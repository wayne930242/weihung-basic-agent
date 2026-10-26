import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import monitorHold, { EXIT_HOLD_CHANNEL } from "../pi/extensions/monitor-hold.ts";

function harness() {
  const handlers = new Map();
  const bus = new EventEmitter();
  const sent = [];
  let timers = [];
  const state = { idle: true };
  const pi = {
    on: (event, handler) => handlers.set(event, handler),
    events: { emit: (channel, data) => bus.emit(channel, data), on: (channel, handler) => bus.on(channel, handler) },
    sendUserMessage: (message) => sent.push(message),
  };
  monitorHold(pi, { setTimeout: (callback) => timers.push(callback) });
  handlers.get("session_start")({}, { isIdle: () => state.idle });
  const flush = () => { const due = timers; timers = []; due.forEach((callback) => callback()); };
  // The probe pi-herdr-agents' isExitHeld sends before a child auto-exits.
  const exitHeld = () => { const probe = { messages: [], hold: false }; bus.emit(EXIT_HOLD_CHANNEL, probe); return probe.hold; };
  const started = (monitorId, description) => bus.emit("monitor:started", { monitorId, command: "bash run.sh", description, timestamp: 1 });
  const finished = (monitorId, extra) => bus.emit("monitor:finished", { monitorId, outputLines: 3, ...extra });
  return { handlers, sent, state, flush, exitHeld, started, finished };
}

test("a child with no running monitor exits as before", () => {
  const h = harness();
  assert.equal(h.exitHeld(), false);
  h.started("m1", "unit tests");
  h.finished("m1", { status: "completed", exitCode: 0 });
  assert.equal(h.exitHeld(), false);
  h.flush();
  assert.deepEqual(h.sent, [], "a monitor that finished while the worker was in its turn needs no wake");
});

test("a running monitor holds the exit, prompts once, and wakes the worker when it finishes", () => {
  const h = harness();
  h.started("m1", "dotnet test");
  h.started("m2", "claude -p reviewer");
  assert.equal(h.exitHeld(), true);
  h.flush();
  assert.equal(h.sent.length, 1);
  assert.match(h.sent[0], /m1: dotnet test\n- m2: claude -p reviewer/);

  assert.equal(h.exitHeld(), true, "ending the turn again keeps holding");
  h.flush();
  assert.equal(h.sent.length, 1, "the same monitors are not announced twice");

  h.finished("m1", { status: "completed", exitCode: 1 });
  h.flush();
  assert.match(h.sent[1], /Monitor m1 \(dotnet test\) finished: completed, exit 1/);
  assert.equal(h.exitHeld(), true, "m2 still runs");

  h.finished("m2", { status: "stopped", reason: "timeout" });
  h.flush();
  assert.match(h.sent[2], /m2 .* finished: stopped, timeout/);
  assert.equal(h.exitHeld(), false, "with nothing running the child exits");
});

test("a worker already woken by its own onDone is not prompted again", () => {
  const h = harness();
  h.started("m1", "build");
  h.exitHeld();
  h.flush();
  h.finished("m1", { status: "completed", exitCode: 0 });
  h.state.idle = false;
  h.flush();
  assert.equal(h.sent.length, 1, "only the hold prompt was sent");
});

test("a hold prompt dropped while another wake runs is sent at the next hold", () => {
  const h = harness();
  h.started("m1", "hold probe");
  h.exitHeld();
  h.state.idle = false;
  h.flush();
  assert.deepEqual(h.sent, [], "pi-loop-monitor's started notice took the turn");
  h.state.idle = true;
  assert.equal(h.exitHeld(), true);
  h.flush();
  assert.match(h.sent[0], /Your turn ended while monitors/);
});

test("session shutdown forgets the monitors pi-loop-monitor stops with it", () => {
  const h = harness();
  h.started("m1", "dev server");
  h.handlers.get("session_shutdown")({});
  assert.equal(h.exitHeld(), false);
});

test("the channel matches the one installed pi-herdr-agents asks", { skip: !existsSync(herdrChild()) && "pi-herdr-agents not installed" }, () => {
  const source = readFileSync(herdrChild(), "utf-8");
  assert.match(source, new RegExp(`EXIT_HOLD_CHANNEL = "${EXIT_HOLD_CHANNEL}"`));
});

function herdrChild() {
  const agent = process.env.PI_CODING_AGENT_DIR ?? join(homedir(), ".pi/agent");
  return join(agent, "git/github.com/wayne930242/pi-herdr-agents/maestro/adapters/pi/child/subagent-done.ts");
}
