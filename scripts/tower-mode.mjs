#!/usr/bin/env node
// The unattended box's pickup mode (MP-4705). Reads hq's mode, keeps the last known one on disk, and prints one line:
//   mode=run|pause|unknown claim=yes|no read=<ok|http_NNN|bad_body|bad_mode|timeout|network|no_token|file|write> board="<text>"
// Exit 0 when claim=yes, 1 when claim=no. The contract is "What the box does with the answer" in moldplan-center
// apps/infra-dashboard/docs/agent-dev-box-broker.md:
// - only a 200 whose JSON has mode "run" or "pause" changes the mode; every other answer keeps the last known one;
// - after a good 200 the read is stored atomically (temp file, then rename) and loaded on the next run;
// - run is the default only while the state file does not exist; a file that exists but cannot be used claims nothing.
// Environment overrides, for tests: TOWER_MODE_URL, TOWER_MODE_TOKEN_FILE, TOWER_MODE_STATE_FILE, TOWER_MODE_TIMEOUT_MS.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_URL = "https://hq.moldplan.app/api/agent-dev/box/mode";
const DEFAULT_TIMEOUT_MS = 5000;
const MAX_BODY_BYTES = 64 * 1024;
const MODES = ["run", "pause"];

export function defaultPaths(home = os.homedir()) {
  return {
    token: path.join(home, ".config/moldplan/agent-dev-box-token"),
    state: path.join(home, ".local/state/agent-tower/tower-mode.json"),
  };
}

/** Write the state file through a temp file in the same directory and a rename, so a reader never sees a partial file. */
export function writeStateAtomic(file, state, io = fs) {
  const directory = path.dirname(file);
  io.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const temp = path.join(directory, `.${path.basename(file)}.${process.pid}.tmp`);
  const data = `${JSON.stringify(state)}\n`;
  let descriptor;
  try {
    descriptor = io.openSync(temp, "w", 0o600);
    io.writeSync(descriptor, data);
    io.fsyncSync(descriptor);
    io.closeSync(descriptor);
    descriptor = undefined;
    io.renameSync(temp, file);
  } catch (error) {
    if (descriptor !== undefined) {
      try { io.closeSync(descriptor); } catch { /* the original error is the one that matters */ }
    }
    try { io.rmSync(temp, { force: true }); } catch { /* nothing more to clean */ }
    throw error;
  }
}

/** The stored read: absent (never read), or the parsed state, or unreadable (exists but cannot be used). */
export function loadState(file, io = fs) {
  let text;
  try {
    text = io.readFileSync(file, "utf8");
  } catch (error) {
    return error?.code === "ENOENT" ? { kind: "absent" } : { kind: "unreadable" };
  }
  try {
    const value = JSON.parse(text);
    const valid = value !== null && typeof value === "object" && !Array.isArray(value)
      && MODES.includes(value.mode)
      && (value.setAt === null || typeof value.setAt === "string")
      && typeof value.readAt === "string";
    return valid ? { kind: "present", state: value } : { kind: "unreadable" };
  } catch {
    return { kind: "unreadable" };
  }
}

async function readBody(response) {
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      throw new Error("body too large");
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/** One read of hq: {ok: true, mode, setAt} for a good 200, else {ok: false, reason}. */
export async function readHq({ url, tokenFile, timeoutMs }) {
  let token;
  try {
    token = fs.readFileSync(tokenFile, "utf8").trim();
  } catch {
    return { ok: false, reason: "no_token" };
  }
  if (!token) return { ok: false, reason: "no_token" };
  const signal = AbortSignal.timeout(timeoutMs);
  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "manual",
      signal,
      headers: { authorization: `Bearer ${token}`, accept: "application/json" },
    });
    if (response.status !== 200) {
      await response.body?.cancel().catch(() => undefined);
      return { ok: false, reason: `http_${response.status}` };
    }
    let body;
    try {
      body = JSON.parse(await readBody(response));
    } catch (error) {
      if (signal.aborted) throw error;
      return { ok: false, reason: "bad_body" };
    }
    if (body === null || typeof body !== "object" || !MODES.includes(body.mode)) {
      return { ok: false, reason: typeof body === "object" && body !== null && "mode" in body ? "bad_mode" : "bad_body" };
    }
    return { ok: true, mode: body.mode, setAt: typeof body.setAt === "string" ? body.setAt : null };
  } catch {
    return { ok: false, reason: signal.aborted ? "timeout" : "network" };
  }
}

function readUnreadSince(file, now, io = fs) {
  try {
    const since = JSON.parse(io.readFileSync(file, "utf8")).since;
    if (typeof since === "string" && !Number.isNaN(Date.parse(since))) return since;
  } catch { /* missing or damaged: this read is the first known failure */ }
  try {
    writeStateAtomic(file, { since: now }, io);
  } catch { /* the time is a board detail; a failed write must not change the answer */ }
  return now;
}

function clearUnreadSince(file, io = fs) {
  try { io.rmSync(file, { force: true }); } catch { /* a stale time is replaced by the next good read */ }
}

/** The whole decision for one run. Returns the fields of the printed line. */
export async function decide({ url, tokenFile, stateFile, timeoutMs, now = new Date().toISOString() }) {
  const unreadFile = `${stateFile}.unread`;
  const stored = loadState(stateFile);
  if (stored.kind === "unreadable") {
    return { mode: "unknown", claim: "no", read: "file", board: "tower-mode file unreadable" };
  }
  const answer = await readHq({ url, tokenFile, timeoutMs });
  if (answer.ok) {
    try {
      writeStateAtomic(stateFile, { mode: answer.mode, setAt: answer.setAt, readAt: now });
    } catch {
      return { mode: answer.mode, claim: "no", read: "write", board: "tower-mode file not writable" };
    }
    clearUnreadSince(unreadFile);
    const claim = answer.mode === "run" ? "yes" : "no";
    const board = answer.mode === "run" ? "" : answer.setAt ? `paused at ${answer.setAt}` : "paused (set time unknown)";
    return { mode: answer.mode, claim, read: "ok", board };
  }
  const mode = stored.kind === "present" ? stored.state.mode : "run";
  const since = readUnreadSince(unreadFile, now);
  return {
    mode,
    claim: mode === "run" ? "yes" : "no",
    read: answer.reason,
    board: `mode ${mode} (cached, hq unread since ${since})`,
  };
}

export function formatLine({ mode, claim, read, board }) {
  return `mode=${mode} claim=${claim} read=${read} board="${board.replaceAll('"', "'")}"`;
}

async function main() {
  const defaults = defaultPaths();
  const timeout = Number(process.env.TOWER_MODE_TIMEOUT_MS);
  const result = await decide({
    url: process.env.TOWER_MODE_URL || DEFAULT_URL,
    tokenFile: process.env.TOWER_MODE_TOKEN_FILE || defaults.token,
    stateFile: process.env.TOWER_MODE_STATE_FILE || defaults.state,
    timeoutMs: Number.isFinite(timeout) && timeout > 0 ? timeout : DEFAULT_TIMEOUT_MS,
  });
  process.stdout.write(`${formatLine(result)}\n`);
  process.exitCode = result.claim === "yes" ? 0 : 1;
}

const invokedDirectly = process.argv[1] && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url));
if (invokedDirectly) {
  main().catch(() => {
    // Anything unforeseen claims nothing; the line still parses.
    process.stdout.write(`${formatLine({ mode: "unknown", claim: "no", read: "file", board: "tower-mode check failed" })}\n`);
    process.exitCode = 1;
  });
}
