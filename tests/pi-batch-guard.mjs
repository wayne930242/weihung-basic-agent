import assert from "node:assert/strict";
import { test } from "node:test";
import batchGuard from "../pi/extensions/batch-guard.ts";

function harness() {
  const handlers = new Map();
  batchGuard({ on: (event, handler) => handlers.set(event, handler) });
  // One assistant message with these tool calls, then pi asks about each call.
  const send = (...calls) => {
    const content = calls.map(([name, input], i) => ({ type: "toolCall", id: `c${i}`, name, arguments: input }));
    handlers.get("message_end")({ type: "message_end", message: { role: "assistant", content } });
    return calls.map((_, i) => handlers.get("tool_call")({ type: "tool_call", toolCallId: `c${i}` }, { cwd: "/repo" }));
  };
  return { send };
}

const monitor = (command) => ["MonitorCreate", { command, description: "probe" }];
const bash = (command) => ["bash", { command }];
const write = (path) => ["write", { path, content: "echo hi\n" }];

test("a monitor that runs a script written in the same batch is blocked (2026-10-17 exit 127)", () => {
  const [writeResult, monitorResult] = harness().send(write("/tmp/collect.sh"), monitor("bash /tmp/collect.sh > /tmp/collect.log 2>&1"));
  assert.equal(writeResult, undefined);
  assert.equal(monitorResult.block, true);
  assert.match(monitorResult.reason, /\/tmp\/collect\.sh, which the write call in the same batch creates/);
});

test("a monitor that reads a prompt a sibling heredoc writes is blocked", () => {
  const [, result] = harness().send(bash("cat > /tmp/review-prompt.md <<'EOF'\nreview the diff\nEOF"), monitor('claude -p "$(cat /tmp/review-prompt.md)"'));
  assert.equal(result.block, true);
});

test("a monitor writing a file a sibling rm deletes is blocked", () => {
  const [, result] = harness().send(bash("rm -f /tmp/review-out.md"), monitor("claude -p review > /tmp/review-out.md"));
  assert.equal(result.block, true);
  assert.match(result.reason, /deletes/);
});

test("running a relative script written in the same batch is blocked", () => {
  const [, result] = harness().send(write("scripts/probe.sh"), bash("bash /repo/scripts/probe.sh"));
  assert.equal(result.block, true);
});

test("unrelated parallel calls, one-call sequences, and later messages pass", () => {
  const h = harness();
  assert.deepEqual(h.send(write("/tmp/a.sh"), bash("ls /tmp/other")), [undefined, undefined]);
  assert.deepEqual(h.send(bash("cat > /tmp/b.sh <<'EOF'\necho\nEOF\nbash /tmp/b.sh")), [undefined]);
  assert.deepEqual(h.send(bash("python3 tests/x.py 2>&1 >/dev/null"), monitor("tail -n 5 /dev/null")), [undefined, undefined]);
  h.send(write("/tmp/c.sh"));
  assert.deepEqual(h.send(monitor("bash /tmp/c.sh")), [undefined]);
});
