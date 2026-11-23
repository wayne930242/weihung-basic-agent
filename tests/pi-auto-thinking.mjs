import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { createAutoThinking, jevClassifier, preprocessPrompt, typesafeApiKey } from "../pi/extensions/auto-thinking.ts";

function harness(classify, { isSubagent = false, solutionSpace } = {}) {
  const handlers = new Map();
  const commands = new Map();
  const state = { level: "medium", statuses: [], notices: [], prompts: [] };
  createAutoThinking(classify, { isSubagent, solutionSpace })({
    on: (event, fn) => handlers.set(event, fn),
    registerCommand: (name, options) => commands.set(name, options),
    setThinkingLevel: (level) => { state.level = level === "max" ? "xhigh" : level; },
    getThinkingLevel: () => state.level,
  });
  const ctx = {
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
  assert.match(h.state.notices.at(-1).message, /kept high: TypeSafe classification failed/);
});

test("failure before any classification leaves the level unchanged", async () => {
  const h = harness(async () => { throw new Error("no key"); });
  await h.prompt("anything");
  assert.equal(h.state.level, "medium");
  assert.match(h.state.notices.at(-1).message, /level unchanged: TypeSafe classification failed/);
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
  assert.match(h.state.notices.at(-1).message, /level unchanged: TypeSafe classification failed/);
});

test("prompt cleanup strips code, tags, hashes and bounds length", () => {
  const cleaned = preprocessPrompt("fix bug in 0123456789abcdef0123 <ctx>noise</ctx>\n```\ncode\n```\nplease");
  assert.equal(cleaned, "fix bug in 0123456 \n \nplease");
  assert.ok(preprocessPrompt("x".repeat(10_000)).length <= 2000);
});

function jevEnvFile(text) {
  const configHome = mkdtempSync(join(tmpdir(), "auto-thinking-"));
  mkdirSync(join(configHome, "pi-jev-compaction"));
  writeFileSync(join(configHome, "pi-jev-compaction", "env"), text);
  return configHome;
}

test("the API key comes from the environment before pi-jev-compaction's env file", () => {
  const configHome = jevEnvFile("TYPESAFE_API_KEY=from-file\n");
  assert.equal(typesafeApiKey({ TYPESAFE_API_KEY: "from-env", XDG_CONFIG_HOME: configHome }), "from-env");
  assert.equal(typesafeApiKey({ XDG_CONFIG_HOME: configHome }), "from-file");
});

test("the env file key may be quoted or exported, and other lines are ignored", () => {
  assert.equal(typesafeApiKey({ XDG_CONFIG_HOME: jevEnvFile("# key\nOTHER=x\nTYPESAFE_API_KEY=\"q v\"\n") }), "q v");
  assert.equal(typesafeApiKey({ XDG_CONFIG_HOME: jevEnvFile("export TYPESAFE_API_KEY='s'\n") }), "s");
  assert.equal(typesafeApiKey({ XDG_CONFIG_HOME: jevEnvFile("OTHER=x\n") }), undefined);
  assert.equal(typesafeApiKey({ XDG_CONFIG_HOME: join(tmpdir(), "no-such-auto-thinking-dir") }), undefined);
});

const fakeKey = "fixture-key";
const fakePrompt = "fixture prompt must not appear in warnings";
const official = "https://api.typesafe.ai";
const custom = "https://custom.invalid";
const conflict = /TYPESAFE_BASE_URL requires an explicit TYPESAFE_API_KEY/;

function mockJev(t, baseUrl, apiKey, fetchStub) {
  const config = { TYPESAFE_BASE_URL: baseUrl, TYPESAFE_API_KEY: apiKey,
    XDG_CONFIG_HOME: jevEnvFile(`TYPESAFE_API_KEY=${fakeKey}\n`) };
  for (const [key, value] of Object.entries(config)) {
    const previous = process.env[key];
    const set = (entry) => { if (entry === undefined) delete process.env[key]; else process.env[key] = entry; };
    t.after(() => set(previous));
    set(value);
  }
  return t.mock.method(globalThis, "fetch", fetchStub);
}

const workingResponse = () => Response.json({ answers: { level: { choice: "high" } } });
const mainHarness = () => harness(jevClassifier());
const childHarness = () => harness(jevClassifier(), { isSubagent: true, solutionSpace: fakePrompt });

test("endpoint conflict is rejected before looking up the file path", () => {
  let lookedUpPath = false;
  const env = { TYPESAFE_BASE_URL: custom,
    get XDG_CONFIG_HOME() { lookedUpPath = true; return tmpdir(); } };
  assert.throws(() => typesafeApiKey(env), conflict);
  assert.equal(lookedUpPath, false);
});

test("a file key with a custom endpoint makes no fetch from either handler", async (t) => {
  const fetch = mockJev(t, custom, undefined, workingResponse);
  const handlers = [mainHarness(), childHarness()];
  for (const h of handlers) await h.prompt(fakePrompt);
  assert.equal(fetch.mock.callCount(), 0);
  for (const h of handlers) {
    assert.equal(h.state.level, "medium");
    assert.match(h.state.notices[0].message, conflict);
  }
});

for (const [label, baseUrl, apiKey, expectedUrl, expectedKey] of [
  ["default official endpoint with file key", undefined, undefined, official, fakeKey],
  ["explicit official endpoint with trailing slashes and file key", `${official}//`, undefined, official, fakeKey],
  ["custom endpoint with explicit env key", custom, "fixture-env-key", custom, "fixture-env-key"],
]) {
  test(label, async (t) => {
    const fetch = mockJev(t, baseUrl, apiKey, workingResponse);
    const h = mainHarness();
    await h.prompt(fakePrompt);
    assert.equal(fetch.mock.callCount(), 1);
    const [url, init] = fetch.mock.calls[0].arguments;
    assert.equal(url, `${expectedUrl}/v1/systemone`);
    assert.equal(init.headers.Authorization, `Bearer ${expectedKey}`);
    assert.equal(h.state.level, "high");
    assert.equal(h.state.notices.length, 0);
  });
}

for (const [label, baseUrl, apiKey, makeHarness] of [
  ["official file-key", undefined, undefined, mainHarness],
  ["custom env-key", custom, "fixture-env-key", childHarness],
]) {
  test(`${label} request rejects redirects`, async (t) => {
    const fetch = mockJev(t, baseUrl, apiKey, (_url, init) => {
      if (init.redirect === "error") throw new TypeError("redirect mode is set to error");
      return workingResponse();
    });
    const h = makeHarness();
    await h.prompt(fakePrompt);
    assert.equal(fetch.mock.calls[0].arguments[1].redirect, "error");
    assert.equal(h.state.level, "medium");
  });
}

const echoed = `${fakeKey} ${fakePrompt}`;
for (const [label, fetchStub, reason] of [
  ["transport exception", () => { throw new TypeError(echoed); }, "TypeSafe request failed"],
  ["HTTP error body", () => new Response(echoed, { status: 401 }), "TypeSafe HTTP 401"],
  ["JSON parsing error", () => new Response(echoed), "Invalid TypeSafe response"],
  ["unexpected choice", () => Response.json({ answers: { level: { choice: echoed } } }), "Unexpected TypeSafe answer"],
  ["inherited choice", () => Response.json({ answers: { level: { choice: "constructor" } } }), "Unexpected TypeSafe answer"],
]) {
  test(`both warnings sanitize ${label}`, async (t) => {
    const fetch = mockJev(t, undefined, undefined, fetchStub);
    const handlers = [mainHarness(), childHarness()];
    for (const h of handlers) await h.prompt(fakePrompt);
    assert.equal(fetch.mock.callCount(), 2);
    for (const h of handlers) {
      assert.equal(h.state.level, "medium");
      assert.equal(h.state.notices.length, 1);
      const [{ message, level }] = h.state.notices;
      assert.equal(level, "warning");
      assert.equal(message.split(": ").at(-1), reason);
      assert.ok(!message.includes(fakeKey) && !message.includes(fakePrompt));
    }
  });
}
