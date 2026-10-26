import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { homedir } from "node:os";
import { isAbsolute, resolve } from "node:path";

// Pi runs the tool calls of one assistant message in parallel, so a call that uses a file another
// call in the same message creates or deletes races it: monitors have started before their script
// existed (exit 127), read an empty prompt, and written into a file a sibling rm then removed.

type Call = { id: string; name: string; input: Record<string, unknown> };
type Change = { callId: string; path: string; verb: "creates" | "deletes" };

const CONSUMERS = new Set(["bash", "MonitorCreate"]);
const REDIRECT = /(?<![0-9&<])>>?\s*(?!&)("[^"]+"|'[^']+'|[^\s;&|()<>]+)/g;
const TEE = /\btee\s+(?:-a\s+)?("[^"]+"|'[^']+'|[^\s;&|()<>]+)/g;
const RM = /(?:^|[\n;&|(])\s*rm\s+((?:-\S+\s+)*)([^\n;&|()]+)/g;

function unquote(token: string): string {
  return token.replace(/^(["'])(.*)\1$/, "$2");
}

function command(input: Record<string, unknown>): string {
  return typeof input.command === "string" ? input.command : "";
}

/** Files a call creates or deletes, as written in the call. */
export function changes(call: Call): Change[] {
  const found: Change[] = [];
  if (call.name === "write" && typeof call.input.path === "string") found.push({ callId: call.id, path: call.input.path, verb: "creates" });
  if (call.name !== "bash") return found;
  const text = command(call.input);
  for (const match of text.matchAll(REDIRECT)) found.push({ callId: call.id, path: unquote(match[1]), verb: "creates" });
  for (const match of text.matchAll(TEE)) found.push({ callId: call.id, path: unquote(match[1]), verb: "creates" });
  for (const match of text.matchAll(RM)) {
    for (const token of match[2].trim().split(/\s+/)) found.push({ callId: call.id, path: unquote(token), verb: "deletes" });
  }
  return found.filter((change) => change.path !== "/dev/null" && change.path !== "" && !change.path.includes("$"));
}

/** The spellings a command could use for `path`: as written, absolute, and with `~`. */
function spellings(path: string, cwd: string): string[] {
  const home = homedir();
  const expanded = path.replace(/^~(?=$|\/)/, home);
  const absolute = isAbsolute(expanded) ? expanded : resolve(cwd, expanded);
  const forms = new Set([path, absolute]);
  if (absolute.startsWith(`${home}/`)) forms.add(`~${absolute.slice(home.length)}`);
  return [...forms];
}

/** The sibling change `call` races, if any. */
export function conflict(call: Call, batch: Call[], cwd: string): Change | undefined {
  if (!CONSUMERS.has(call.name)) return undefined;
  const text = command(call.input);
  if (!text) return undefined;
  for (const sibling of batch) {
    if (sibling.id === call.id) continue;
    for (const change of changes(sibling)) {
      if (spellings(change.path, cwd).some((form) => text.includes(form))) return change;
    }
  }
  return undefined;
}

export function blockReason(call: Call, change: Change, batch: Call[]): string {
  const sibling = batch.find((candidate) => candidate.id === change.callId);
  return [
    `Blocked: this ${call.name} call uses ${change.path}, which the ${sibling?.name ?? "other"} call in the same batch ${change.verb}.`,
    "Tool calls in one message run in parallel, so it may run before that file exists or after it is gone.",
    `Let the ${sibling?.name ?? "other"} call finish (check the file with ls if it matters), then make this call in a later message.`,
  ].join(" ");
}

export default function batchGuard(pi: ExtensionAPI): void {
  let batch: Call[] = [];

  pi.on("message_end", (event) => {
    const message = event.message as { role?: string; content?: unknown };
    if (message.role !== "assistant" || !Array.isArray(message.content)) return;
    batch = message.content
      .filter((part): part is { type: string; id: string; name: string; arguments: Record<string, unknown> } => part?.type === "toolCall")
      .map((part) => ({ id: part.id, name: part.name, input: part.arguments ?? {} }));
  });

  pi.on("tool_call", (event, ctx) => {
    if (event.parentToolCallId || batch.length < 2) return;
    const call = batch.find((candidate) => candidate.id === event.toolCallId);
    if (!call) return;
    const change = conflict(call, batch, ctx.cwd);
    if (!change) return;
    return { block: true, reason: blockReason(call, change, batch) };
  });
}
