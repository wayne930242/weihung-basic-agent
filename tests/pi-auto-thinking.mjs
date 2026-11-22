import assert from "node:assert/strict";
import { test } from "node:test";
import autoThinking, { CLASSIFY_TIMEOUT_MS, createAutoThinking, jevClassifier, preprocessPrompt } from "../pi/extensions/auto-thinking.ts";

function harness(classify, { isSubagent = false, solutionSpace, modelRegistry, extension } = {}) {
  const handlers = new Map();
  const commands = new Map();
  const state = { level: "medium", statuses: [], notices: [], prompts: [] };
  (extension ?? createAutoThinking(classify, { isSubagent, solutionSpace }))({
    on: (event, fn) => handlers.set(event, fn),
    registerCommand: (name, options) => commands.set(name, options),
    setThinkingLevel: (level) => { state.level = level === "max" ? "xhigh" : level; },
    getThinkingLevel: () => state.level,
  });
  const ctx = {
    modelRegistry,
    ui: {
      setStatus: (_key, text) => state.statuses.push(text),
      notify: (message, level) => state.notices.push({ message, level }),
    },
  };
  const prompt = (text) => handlers.get("before_agent_start")({ type: "before_agent_start", messageType: "user", prompt: text }, ctx);
  const custom = () => handlers.get("before_agent_start")({ type: "before_agent_start", messageType: "custom", message: { role: "custom" } }, ctx);
  const select = (level) => handlers.get("thinking_level_select")({ level, previousLevel: state.level }, ctx);
  const command = (args) => commands.get("auto-thinking").handler(args, ctx);
  return { handlers, state, prompt, custom, select, command };
}

test("classified level becomes the thinking level", async () => {
  const seen = [];
  const h = harness(async (input) => { seen.push(input); return "xhigh"; });
  await h.prompt("diagnose an intermittent deadlock");
  assert.equal(h.state.level, "xhigh");
  assert.deepEqual(seen, [{ request: "diagnose an intermittent deadlock" }]);
  assert.equal(h.state.statuses.at(-1), "auto:xhigh");
});

test("ultrathink skips the classifier and asks for max", async () => {
  const h = harness(async () => { throw new Error("must not classify"); });
  await h.prompt("ultrathink about this migration");
  assert.equal(h.state.level, "xhigh");
});

test("failure keeps the last classified level and warns", async () => {
  let fail = false;
  const h = harness(async () => { if (fail) throw new Error("timeout"); return "high"; });
  await h.prompt("pick an API shape");
  fail = true;
  h.state.level = "low";
  await h.prompt("rename a constant");
  assert.equal(h.state.level, "high");
  assert.match(h.state.notices.at(-1).message, /kept high: timeout/);
});

test("failure before any classification leaves the level unchanged", async () => {
  const h = harness(async () => { throw new Error("no key"); });
  await h.prompt("anything");
  assert.equal(h.state.level, "medium");
  assert.match(h.state.notices.at(-1).message, /level unchanged: no key/);
});

test("a run started by a custom message keeps the level without classifying", async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return "high"; });
  await h.prompt("pick an API shape");
  h.state.level = "low";
  await h.custom();
  assert.equal(calls, 1);
  assert.equal(h.state.level, "low");
  assert.equal(h.state.notices.length, 0);
});

test("manual level change turns auto off until /auto-thinking on", async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return "low"; });
  await h.prompt("rename");
  await h.select("low");
  assert.equal(h.state.notices.length, 0, "its own level change is not manual");
  await h.select("high");
  assert.match(h.state.notices.at(-1).message, /auto-thinking off/);
  await h.prompt("rename again");
  assert.equal(calls, 1);
  await h.command("on");
  await h.prompt("rename once more");
  assert.equal(calls, 2);
});

test("subagents without a solution space register nothing", () => {
  const h = harness(async () => "low", { isSubagent: true });
  assert.equal(h.handlers.size, 0);
});

test("a subagent classifies its solution space once, not its task", async () => {
  const seen = [];
  const h = harness(async (input) => { seen.push(input); return "high"; },
    { isSubagent: true, solutionSpace: "Cause known; the fix needs one API choice." });
  await h.prompt("a long task text that must not be classified");
  await h.prompt("a follow-up task");
  assert.equal(h.state.level, "high");
  assert.deepEqual(seen, [{ solutionSpace: "Cause known; the fix needs one API choice." }]);
  assert.deepEqual([...h.handlers.keys()], ["before_agent_start"]);
});

test("a failed solution space classification keeps the dispatcher's level", async () => {
  const h = harness(async () => { throw new Error("no key"); }, { isSubagent: true, solutionSpace: "Open cause." });
  await h.prompt("task");
  assert.equal(h.state.level, "medium");
  assert.match(h.state.notices.at(-1).message, /level unchanged: no key/);
});

const FAKE_KEY = "fake-pi-typesafe-key";
const SYSTEM_ONE_URL = "https://api.typesafe.ai/v1/systemone";

function fakeJev(t, { apiKey, baseUrl, model, lookup = async () => FAKE_KEY, reply } = {}) {
  const config = { TYPESAFE_API_KEY: apiKey, TYPESAFE_BASE_URL: baseUrl, TYPESAFE_DEFAULT_MODEL: model };
  const previous = Object.fromEntries(Object.keys(config).map((key) => [key, process.env[key]]));
  const applyEnv = (values) => {
    for (const [key, value] of Object.entries(values)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  };
  t.after(() => applyEnv(previous));
  applyEnv(config);
  const requests = [];
  const providers = [];
  const modelRegistry = {
    async getApiKeyForProvider(provider) {
      providers.push(provider);
      return lookup();
    },
  };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, ...options, body: JSON.parse(options.body) });
    return reply ? reply() : Response.json({ answers: { level: { choice: "high" } } });
  });
  return { modelRegistry, requests, providers };
}

test("main extension uses Pi's TypeSafe key at the explicitly configured first-party endpoint", async (t) => {
  const { modelRegistry, requests, providers } = fakeJev(t, { baseUrl: "https://api.typesafe.ai/" });
  const h = harness(undefined, { extension: autoThinking, modelRegistry });
  await h.prompt("pick an API shape");
  assert.equal(h.state.level, "high");
  assert.deepEqual(providers, ["typesafe"]);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, SYSTEM_ONE_URL);
  assert.equal(requests[0].redirect, "error");
  assert.equal(requests[0].headers.Authorization, `Bearer ${FAKE_KEY}`);
  assert.equal(requests[0].body.model, "jev-latest");
  assert.deepEqual(requests[0].body.state, { request: "pick an API shape" });
});

test("subagent uses Pi's TypeSafe key for its solution space once", async (t) => {
  const { modelRegistry, requests, providers } = fakeJev(t);
  const h = harness(jevClassifier(), { isSubagent: true, solutionSpace: "One local choice.", modelRegistry });
  await h.prompt("not the text to classify");
  await h.prompt("follow-up");
  assert.equal(h.state.level, "high");
  assert.deepEqual(providers, ["typesafe"]);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, SYSTEM_ONE_URL);
  assert.equal(requests[0].headers.Authorization, `Bearer ${FAKE_KEY}`);
  assert.deepEqual(requests[0].body.state, { solution_space: "One local choice." });
});

for (const [path, options] of Object.entries({ main: {}, child: { isSubagent: true, solutionSpace: "One local choice." } })) {
  test(`F001 ${path}: conflicting URL without an explicit env key fails before lookup and fetch`, async (t) => {
    const { modelRegistry, requests, providers } = fakeJev(t, { baseUrl: "https://override.invalid" });
    const h = harness(jevClassifier(), { ...options, modelRegistry });
    await h.prompt("classify this task");
    assert.equal(h.state.level, "medium");
    assert.deepEqual(providers, []);
    assert.deepEqual(requests, []);
    assert.match(h.state.notices[0].message, /TYPESAFE_BASE_URL.*TYPESAFE_API_KEY/);
  });

  for (const lateResult of ["resolve", "reject"]) {
    test(`F002 ${path}: startup settles at the deadline before lookup can ${lateResult}`, async (t) => {
      t.mock.timers.enable({ apis: ["setTimeout"] });
      const childTimeouts = [];
      t.mock.method(AbortSignal, "timeout", (delay) => {
        childTimeouts.push(delay);
        const controller = new AbortController();
        setTimeout(() => controller.abort(), delay);
        return controller.signal;
      });
      const lookup = Promise.withResolvers();
      const { modelRegistry, requests, providers } = fakeJev(t, { lookup: () => lookup.promise });
      const h = harness(jevClassifier(), { ...options, modelRegistry });
      let settled = false;
      void h.prompt("classify this task").then(() => { settled = true; });
      const flush = () => new Promise((resolve) => setImmediate(resolve));
      await flush();
      assert.deepEqual(providers, ["typesafe"]);
      assert.deepEqual(childTimeouts, options.isSubagent ? [CLASSIFY_TIMEOUT_MS] : []);
      t.mock.timers.tick(CLASSIFY_TIMEOUT_MS - 1);
      await flush();
      assert.equal(settled, false);
      t.mock.timers.tick(1);
      await flush();
      assert.equal(settled, true);
      assert.equal(h.state.level, "medium");
      assert.match(h.state.notices[0].message, /timed out/);
      assert.deepEqual(requests, []);
      if (lateResult === "resolve") lookup.resolve(FAKE_KEY);
      else lookup.reject(new Error(FAKE_KEY));
      await flush(); // node:test also fails on an unhandled late rejection.
      assert.deepEqual(requests, []);
      assert.equal(h.state.level, "medium");
      assert.equal(h.state.notices.length, 1);
    });
  }
}

test("explicit env key, base URL and model still take precedence", async (t) => {
  const apiKey = "fake-legacy-env-key";
  const { modelRegistry, requests, providers } = fakeJev(t, {
    apiKey, baseUrl: "https://explicit.invalid/prefix///", model: "jev-example",
  });
  const h = harness(jevClassifier(), { modelRegistry });
  await h.prompt("change a name");
  assert.equal(h.state.level, "high");
  assert.deepEqual(providers, []);
  assert.equal(requests[0].url, "https://explicit.invalid/prefix/v1/systemone");
  assert.equal(requests[0].headers.Authorization, `Bearer ${apiKey}`);
  assert.equal(requests[0].body.model, "jev-example");
});

test("missing credentials leave the level unchanged without a request", async (t) => {
  const { modelRegistry, requests, providers } = fakeJev(t, { lookup: async () => undefined });
  const h = harness(jevClassifier(), { modelRegistry });
  await h.prompt("change a name");
  assert.equal(h.state.level, "medium");
  assert.deepEqual(providers, ["typesafe"]);
  assert.deepEqual(requests, []);
  assert.match(h.state.notices[0].message, /level unchanged/);
});

for (const [name, failure] of Object.entries({
  resolver: { lookup: async () => { throw new Error(FAKE_KEY); } },
  transport: { reply: () => { throw new Error(FAKE_KEY); } },
  HTTP: { reply: () => new Response(FAKE_KEY, { status: 401 }) },
  JSON: { reply: () => new Response(FAKE_KEY) },
  choice: { reply: () => Response.json({ answers: { level: { choice: FAKE_KEY } } }) },
})) {
  test(`${name} failure keeps the previous level without exposing the key`, async (t) => {
    const { modelRegistry, requests } = fakeJev(t, { apiKey: name === "resolver" ? undefined : FAKE_KEY, ...failure });
    const h = harness(jevClassifier(), { modelRegistry });
    await h.prompt("change a name");
    assert.equal(h.state.level, "medium");
    assert.equal(requests.length, name === "resolver" ? 0 : 1);
    assert.equal(h.state.notices.length, 1);
    assert.match(h.state.notices[0].message, /level unchanged/);
    assert.ok(!h.state.notices[0].message.includes(FAKE_KEY));
  });
}

test("prompt cleanup strips code, tags, hashes and bounds length", () => {
  const cleaned = preprocessPrompt("fix bug in 0123456789abcdef0123 <ctx>noise</ctx>\n```\ncode\n```\nplease");
  assert.equal(cleaned, "fix bug in 0123456 \n \nplease");
  assert.ok(preprocessPrompt("x".repeat(10_000)).length <= 2000);
});
