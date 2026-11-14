#!/usr/bin/env node
// The unattended box's pickup mode (MP-4705). Reads hq's mode, keeps the last known one on disk, and prints one line:
//   mode=run|pause|unknown claim=yes|no read=<ok|http_NNN|bad_body|bad_mode|timeout|network|no_token|file|write|error> board="<text>"
// Exit 0 when claim=yes, 1 when claim=no. The contract is "What the box does with the answer" in moldplan-center
// apps/infra-dashboard/docs/agent-dev-box-broker.md:
// - only a 200 whose JSON has mode "run" or "pause" changes the mode; every other answer keeps the last known one;
// - after a good 200 the read is stored atomically (temp file, then rename) and loaded on the next run;
// - run is the default only while the state file does not exist; a file that exists but cannot be used claims nothing;
// - a read that cannot be stored keeps the file when its mode already equals the answer; otherwise it empties the
//   state file (or creates it empty), so the next run claims nothing too.
// Environment overrides, for tests: TOWER_MODE_URL (https, or http to 127.0.0.1 or localhost; anything else is ignored),
// TOWER_MODE_TOKEN_FILE, TOWER_MODE_STATE_FILE, TOWER_MODE_TIMEOUT_MS.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const DEFAULT_URL = "https://hq.moldplan.app/api/agent-dev/box/mode";
const DEFAULT_TIMEOUT_MS = 5000;
const MAX_BODY_BYTES = 64 * 1024;
const MODES = ["run", "pause"];
const ISO_TIME = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,9})?(Z|[+-]\d\d:\d\d)$/;
const MAX_TIME_LENGTH = 40;

/** True for an ISO-8601 date-time with a zone, short enough to print. */
export function isIsoTime(value) {
  return typeof value === "string" && value.length <= MAX_TIME_LENGTH && ISO_TIME.test(value) && !Number.isNaN(Date.parse(value));
}

/** TOWER_MODE_URL is a test seam: honored for https, or http to 127.0.0.1 or localhost; anything else is the default. */
export function resolveUrl(value) {
  if (!value) return DEFAULT_URL;
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return DEFAULT_URL;
  }
  const local = parsed.protocol === "http:" && (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost");
  return parsed.protocol === "https:" || local ? value : DEFAULT_URL;
}

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
  // The rename has taken effect; syncing the directory only makes it survive a power loss.
  try {
    const directoryDescriptor = io.openSync(directory, "r");
    try { io.fsyncSync(directoryDescriptor); } finally { io.closeSync(directoryDescriptor); }
  } catch { /* some filesystems cannot fsync a directory */ }
}

/** Empty the state file (or create it empty) without needing free space, so later runs read it as unreadable. */
function poisonState(file, io = fs) {
  try {
    io.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    io.closeSync(io.openSync(file, "w", 0o600));
  } catch { /* nothing more can be done; this run claims nothing either way */ }
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
      && (value.setAt === null || isIsoTime(value.setAt))
      && isIsoTime(value.readAt);
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
    // Only mode decides (hq contract); a setAt that is not an ISO time is dropped, never printed.
    const setAt = isIsoTime(body.setAt) ? body.setAt : null;
    return { ok: true, mode: body.mode, setAt };
  } catch {
    return { ok: false, reason: signal.aborted ? "timeout" : "network" };
  }
}

function readUnreadSince(file, now, io = fs) {
  try {
    const since = JSON.parse(io.readFileSync(file, "utf8")).since;
    if (isIsoTime(since)) return since;
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
export async function decide({ url, tokenFile, stateFile, timeoutMs, now = new Date().toISOString(), io = fs }) {
  const unreadFile = `${stateFile}.unread`;
  const stored = loadState(stateFile, io);
  if (stored.kind === "unreadable") {
    return { mode: "unknown", claim: "no", read: "file", board: "tower-mode file unreadable" };
  }
  const answer = await readHq({ url, tokenFile, timeoutMs });
  if (answer.ok) {
    // The read was good whether or not it could be stored, so the failure run is over.
    clearUnreadSince(unreadFile, io);
    try {
      writeStateAtomic(stateFile, { mode: answer.mode, setAt: answer.setAt, readAt: now }, io);
    } catch {
      if (stored.kind === "present" && stored.state.mode === answer.mode) {
        // The stored mode is still the answer: keep the file and act on it.
        return { mode: answer.mode, claim: answer.mode === "run" ? "yes" : "no", read: "write", board: `mode ${answer.mode} (tower-mode file not writable)` };
      }
      poisonState(stateFile, io);
      return { mode: answer.mode, claim: "no", read: "write", board: "tower-mode file not writable" };
    }
    const claim = answer.mode === "run" ? "yes" : "no";
    const board = answer.mode === "run" ? "mode run" : answer.setAt ? `paused at ${answer.setAt}` : "paused (set time unknown)";
    return { mode: answer.mode, claim, read: "ok", board };
  }
  const mode = stored.kind === "present" ? stored.state.mode : "run";
  const since = readUnreadSince(unreadFile, now, io);
  const source = stored.kind === "present" ? "cached" : "default";
  return {
    mode,
    claim: mode === "run" ? "yes" : "no",
    read: answer.reason,
    board: `mode ${mode} (${source}, hq unread since ${since})`,
  };
}

const UNPRINTABLE = /[\p{Cc}\p{Zl}\p{Zp}]/gu;
const printable = (text) => String(text).replace(UNPRINTABLE, " ");

export function formatLine({ mode, claim, read, board }) {
  return `mode=${printable(mode)} claim=${printable(claim)} read=${printable(read)} board="${printable(board).replaceAll('"', "'")}"`;
}

/** The line for an error nothing foresaw: claims nothing, and still parses. */
export function failedLine() {
  return formatLine({ mode: "unknown", claim: "no", read: "error", board: "tower-mode check failed" });
}

async function main() {
  const defaults = defaultPaths();
  const timeout = Number(process.env.TOWER_MODE_TIMEOUT_MS);
  const result = await decide({
    url: resolveUrl(process.env.TOWER_MODE_URL),
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
    process.stdout.write(`${failedLine()}\n`);
    process.exitCode = 1;
  });
}
