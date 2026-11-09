import assert from "node:assert/strict";
import lastReply, { formatStamp } from "../pi/extensions/last-reply.ts";

const handlers = new Map();
lastReply({ on(event, handler) { handlers.set(event, handler); } });

assert.equal(formatStamp(new Date(2026, 10, 9, 7, 5)), "last reply 11/09 07:05");

const statuses = [];
let branch = [];
const ctx = {
  hasUI: true,
  sessionManager: { getBranch: () => branch },
  ui: { setStatus: (key, text) => statuses.push([key, text]) },
};

handlers.get("session_start")({ reason: "startup" }, ctx);
assert.equal(statuses.length, 0, "a session without replies shows nothing");

branch = [
  { type: "message", message: { role: "user", timestamp: new Date(2026, 9, 1, 8, 0).getTime() } },
  { type: "message", message: { role: "assistant", timestamp: new Date(2026, 9, 1, 9, 30).getTime() } },
  { type: "message", message: { role: "user", timestamp: new Date(2026, 9, 1, 10, 0).getTime() } },
];
handlers.get("session_start")({ reason: "resume" }, ctx);
assert.deepEqual(statuses.at(-1), ["last-reply", "last reply 10/01 09:30"], "resume uses the last assistant message");

handlers.get("agent_settled")({}, ctx);
assert.deepEqual(statuses.at(-1), ["last-reply", formatStamp(new Date())], "settled run stamps now");

const count = statuses.length;
handlers.get("agent_settled")({}, { ...ctx, hasUI: false });
assert.equal(statuses.length, count, "no UI, no status");

console.log("pi last reply: pass");
