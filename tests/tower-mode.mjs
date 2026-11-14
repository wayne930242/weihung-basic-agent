import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { after, before, beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../scripts/tower-mode.mjs", import.meta.url));
const TOKEN = "mpbox_TESTTOKENTESTTOKENTESTTOKENTESTTOKENTEST123";
const LINE = /^mode=(run|pause|unknown) claim=(yes|no) read=(\S+) board="([^"]*)"$/;

let server;
let base;
let dir;
let paths;
let requests;
let respond;

function json(status, body, headers = {}) {
  return (_req, res) => {
    res.writeHead(status, { "content-type": "application/json", ...headers });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };
}

before(async () => {
  server = http.createServer((req, res) => {
    requests.push({ method: req.method, url: req.url, authorization: req.headers.authorization });
    respond(req, res);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
});

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "tower-mode-"));
  paths = { token: path.join(dir, "token"), state: path.join(dir, "state/tower-mode.json") };
  fs.writeFileSync(paths.token, `${TOKEN}\n`, { mode: 0o600 });
  requests = [];
  respond = json(200, { mode: "run", setAt: null });
});

function run(extra = {}) {
  return new Promise((resolve) => {
    execFile(
      process.execPath,
      [SCRIPT],
      {
        env: {
          PATH: process.env.PATH,
          HOME: dir,
          TOWER_MODE_URL: `${base}/api/agent-dev/box/mode`,
          TOWER_MODE_TOKEN_FILE: paths.token,
          TOWER_MODE_STATE_FILE: paths.state,
          TOWER_MODE_TIMEOUT_MS: "2000",
          ...extra,
        },
      },
      (error, stdout, stderr) => {
        const lines = stdout.split("\n").filter(Boolean);
        assert.equal(lines.length, 1, `exactly one stdout line, got ${JSON.stringify(stdout)}`);
        const match = LINE.exec(lines[0]);
        assert.ok(match, `machine-readable line: ${lines[0]}`);
        assert.ok(!stdout.includes(TOKEN) && !stderr.includes(TOKEN), "the token is never printed");
        const [, mode, claim, read, board] = match;
        const code = error ? error.code : 0;
        assert.equal(code, claim === "yes" ? 0 : 1, "exit code follows claim");
        resolve({ mode, claim, read, board, code, stderr });
      },
    );
  });
}

function store(state) {
  fs.mkdirSync(path.dirname(paths.state), { recursive: true });
  fs.writeFileSync(paths.state, typeof state === "string" ? state : JSON.stringify(state));
}

const stored = () => JSON.parse(fs.readFileSync(paths.state, "utf8"));
const siblings = () => (fs.existsSync(path.dirname(paths.state)) ? fs.readdirSync(path.dirname(paths.state)).sort() : []);
const PAUSED = { mode: "pause", setAt: "2026-11-13T14:00:00.000Z", readAt: "2026-11-14T01:00:00.000Z" };

describe("a good 200", () => {
  test("run: claims, sends the bearer token with GET, and stores the read atomically", async () => {
    respond = json(200, { mode: "run", setAt: null });
    const before = Date.now();
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.read, result.board], ["run", "yes", "ok", ""]);
    assert.deepEqual(requests, [{ method: "GET", url: "/api/agent-dev/box/mode", authorization: `Bearer ${TOKEN}` }]);
    const state = stored();
    assert.equal(state.mode, "run");
    assert.equal(state.setAt, null);
    assert.ok(Date.parse(state.readAt) >= before - 1000 && Date.parse(state.readAt) <= Date.now() + 1000);
    assert.deepEqual(siblings(), ["tower-mode.json"], "no temp file stays behind");
    assert.equal(fs.statSync(paths.state).mode & 0o777, 0o600);
  });

  test("pause: claims nothing and the board names the time it was set", async () => {
    respond = json(200, { mode: "pause", setAt: "2026-11-13T14:00:00.000Z" });
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.read], ["pause", "no", "ok"]);
    assert.equal(result.board, "paused at 2026-11-13T14:00:00.000Z");
    assert.equal(stored().mode, "pause");
    assert.equal(stored().setAt, "2026-11-13T14:00:00.000Z");
  });

  test("a pause whose setAt is null still pauses", async () => {
    respond = json(200, { mode: "pause", setAt: null });
    const result = await run();
    assert.deepEqual([result.mode, result.claim], ["pause", "no"]);
    assert.match(result.board, /^paused/);
  });

  test("run after a stored pause unpauses, and clears the unread time", async () => {
    store(PAUSED);
    respond = json(503, { error: "unavailable" });
    assert.equal((await run()).mode, "pause");
    assert.ok(fs.existsSync(`${paths.state}.unread`));
    respond = json(200, { mode: "run", setAt: "2026-11-14T02:00:00.000Z" });
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.read], ["run", "yes", "ok"]);
    assert.equal(stored().mode, "run");
    assert.equal(fs.existsSync(`${paths.state}.unread`), false);
  });
});

describe("any other answer keeps the last known mode", () => {
  const failures = {
    "404": json(404, "<html>Next 404</html>"),
    "401": json(401, { error: "unauthorized" }),
    "403": json(403, { error: "forbidden" }),
    "500": json(500, "boom"),
    "503": json(503, { error: "unavailable" }),
    "a redirect": json(302, "", { location: "/elsewhere" }),
    "a 200 that does not parse": json(200, "<html>not json</html>"),
    "a 200 that is not an object": json(200, "[\"run\"]"),
    "a 200 with another mode": json(200, { mode: "maintenance", setAt: null }),
    "a 200 with the wrong case": json(200, { mode: "RUN", setAt: null }),
    "a 200 without a mode": json(200, { setAt: null }),
  };

  for (const [name, handler] of Object.entries(failures)) {
    test(`${name}: a stored pause stays a pause and the file is untouched`, async () => {
      store(PAUSED);
      const bytes = fs.readFileSync(paths.state);
      respond = handler;
      const result = await run();
      assert.deepEqual([result.mode, result.claim], ["pause", "no"]);
      assert.notEqual(result.read, "ok");
      assert.match(result.board, /^mode pause \(cached, hq unread since \d{4}-\d\d-\d\dT[\d:.]+Z\)$/);
      assert.deepEqual(fs.readFileSync(paths.state), bytes, "only a good 200 writes the state file");
    });

    test(`${name}: a stored run stays a run`, async () => {
      store({ mode: "run", setAt: null, readAt: "2026-11-14T01:00:00.000Z" });
      respond = handler;
      const result = await run();
      assert.deepEqual([result.mode, result.claim], ["run", "yes"]);
      assert.match(result.board, /^mode run \(cached, hq unread since /);
    });
  }

  test("no state file: run is the default, and no state file appears", async () => {
    respond = json(404, "<html>Next 404</html>");
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.read], ["run", "yes", "http_404"]);
    assert.equal(fs.existsSync(paths.state), false);
  });

  test("a redirect is not followed", async () => {
    store(PAUSED);
    respond = (req, res) => {
      if (req.url === "/target") return json(200, { mode: "run", setAt: null })(req, res);
      res.writeHead(302, { location: "/target" });
      res.end();
    };
    const result = await run();
    assert.deepEqual([result.mode, result.read], ["pause", "http_302"]);
    assert.deepEqual(requests.map((r) => r.url), ["/api/agent-dev/box/mode"], "the target was never requested");
  });

  test("a timeout keeps a stored pause", async () => {
    store(PAUSED);
    respond = () => {};
    const started = Date.now();
    const result = await run({ TOWER_MODE_TIMEOUT_MS: "300" });
    assert.deepEqual([result.mode, result.claim, result.read], ["pause", "no", "timeout"]);
    assert.ok(Date.now() - started < 5000);
  });

  test("a body that stalls after the headers is a timeout too", async () => {
    store(PAUSED);
    respond = (_req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.write("{\"mode\":");
    };
    const result = await run({ TOWER_MODE_TIMEOUT_MS: "300" });
    assert.deepEqual([result.mode, result.claim, result.read], ["pause", "no", "timeout"]);
  });

  test("a refused connection keeps a stored pause", async () => {
    store(PAUSED);
    const result = await run({ TOWER_MODE_URL: "http://127.0.0.1:1/api/agent-dev/box/mode" });
    assert.deepEqual([result.mode, result.claim, result.read], ["pause", "no", "network"]);
  });

  test("a missing token file is a failed read, not a run", async () => {
    store(PAUSED);
    fs.rmSync(paths.token);
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.read], ["pause", "no", "no_token"]);
    assert.equal(requests.length, 0);
  });

  test("an empty token file is a failed read", async () => {
    fs.writeFileSync(paths.token, "\n");
    const result = await run();
    assert.equal(result.read, "no_token");
    assert.equal(requests.length, 0);
  });

  test("the first failed read's time is kept across later failures and reset by a good 200", async () => {
    store(PAUSED);
    respond = json(503, {});
    const first = await run();
    const since = /since (\S+)\)/.exec(first.board)[1];
    await new Promise((resolve) => setTimeout(resolve, 20));
    const second = await run();
    assert.equal(/since (\S+)\)/.exec(second.board)[1], since);
    respond = json(200, { mode: "pause", setAt: "2026-11-13T14:00:00.000Z" });
    await run();
    respond = json(503, {});
    const third = await run();
    assert.notEqual(/since (\S+)\)/.exec(third.board)[1], since);
  });
});

describe("a state file that exists but cannot be used", () => {
  const broken = {
    garbage: "not json {",
    empty: "",
    "an array": "[]",
    "an unknown mode": JSON.stringify({ mode: "maybe", setAt: null, readAt: "2026-11-14T01:00:00.000Z" }),
    "no mode": JSON.stringify({ setAt: null, readAt: "2026-11-14T01:00:00.000Z" }),
    "a truncated write": '{"mode":"pau',
  };

  for (const [name, content] of Object.entries(broken)) {
    test(`${name}: claims nothing, asks hq nothing, leaves the file alone`, async () => {
      store(content);
      respond = json(200, { mode: "run", setAt: null });
      const result = await run();
      assert.deepEqual([result.mode, result.claim, result.read, result.board], ["unknown", "no", "file", "tower-mode file unreadable"]);
      assert.equal(requests.length, 0, "a corrupt file must not be unpaused by a read");
      assert.equal(fs.readFileSync(paths.state, "utf8"), content);
    });
  }

  test("a state path that is a directory is unreadable", async () => {
    fs.mkdirSync(paths.state, { recursive: true });
    const result = await run();
    assert.deepEqual([result.mode, result.claim, result.board], ["unknown", "no", "tower-mode file unreadable"]);
  });
});

describe("a read that cannot be stored", () => {
  test("claims nothing and leaves the old state in place", async () => {
    store({ mode: "run", setAt: null, readAt: "2026-11-14T01:00:00.000Z" });
    const stateDir = path.dirname(paths.state);
    const bytes = fs.readFileSync(paths.state);
    respond = json(200, { mode: "run", setAt: null });
    fs.chmodSync(stateDir, 0o500);
    try {
      if (process.getuid?.() === 0) return;
      const result = await run();
      assert.deepEqual([result.mode, result.claim, result.read], ["run", "no", "write"]);
      assert.match(result.board, /not writable/);
    } finally {
      fs.chmodSync(stateDir, 0o700);
    }
    assert.deepEqual(fs.readFileSync(paths.state), bytes);
    assert.deepEqual(siblings(), ["tower-mode.json"]);
  });
});

describe("the atomic write", () => {
  test("a failed rename or a half write leaves the old file and no temp file", async () => {
    const { writeStateAtomic } = await import(SCRIPT);
    store(PAUSED);
    const bytes = fs.readFileSync(paths.state);
    const next = { mode: "run", setAt: null, readAt: "2026-11-14T03:00:00.000Z" };

    const failingRename = { ...fs, renameSync: () => { throw new Error("rename failed"); } };
    assert.throws(() => writeStateAtomic(paths.state, next, failingRename), /rename failed/);
    assert.deepEqual(fs.readFileSync(paths.state), bytes);
    assert.deepEqual(siblings(), ["tower-mode.json"]);

    const halfWrite = {
      ...fs,
      writeSync: (fd, data, ...rest) => {
        fs.writeSync(fd, String(data).slice(0, 5), ...rest);
        throw new Error("disk full");
      },
    };
    assert.throws(() => writeStateAtomic(paths.state, next, halfWrite), /disk full/);
    assert.deepEqual(fs.readFileSync(paths.state), bytes);
    assert.deepEqual(siblings(), ["tower-mode.json"]);

    writeStateAtomic(paths.state, next);
    assert.deepEqual(stored(), next);
    assert.deepEqual(siblings(), ["tower-mode.json"]);
  });

  test("the temp file is renamed into place, never written in place", async () => {
    const { writeStateAtomic } = await import(SCRIPT);
    store(PAUSED);
    const calls = [];
    const recording = {
      ...fs,
      openSync: (file, ...rest) => { calls.push(["open", path.basename(file)]); return fs.openSync(file, ...rest); },
      renameSync: (from, to) => { calls.push(["rename", path.basename(from), path.basename(to)]); return fs.renameSync(from, to); },
    };
    writeStateAtomic(paths.state, { mode: "run", setAt: null, readAt: "x" }, recording);
    assert.notEqual(calls[0][1], "tower-mode.json");
    assert.deepEqual(calls.at(-1).slice(2), ["tower-mode.json"]);
  });
});
