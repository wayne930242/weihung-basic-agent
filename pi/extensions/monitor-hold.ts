import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

// pi-herdr-agents asks this channel before a child exits on a settled run.
export const EXIT_HOLD_CHANNEL = "pi-herdr-agents:exit-hold";
// Let the turn settle before prompting, so the message starts a new run instead of queueing.
export const PROMPT_DELAY_MS = 2_000;

type Monitor = { id: string; label: string };
type Finished = { monitorId?: string; status?: string; exitCode?: number; reason?: string; error?: string };

export type MonitorHoldDeps = { setTimeout: (callback: () => void, ms: number) => void };
const defaultDeps: MonitorHoldDeps = { setTimeout: (callback, ms) => void setTimeout(callback, ms) };

export function heldPrompt(monitors: Monitor[]): string {
  const list = monitors.map((monitor) => `- ${monitor.id}: ${monitor.label}`).join("\n");
  return [
    "Your turn ended while monitors you started are still running, so this subagent stays open instead of exiting and killing them:",
    list,
    "Their results are part of your task. You will be woken as each one finishes; read its output with MonitorList and continue. Stop any monitor you no longer need with MonitorStop, then finish the task.",
  ].join("\n");
}

export function finishedPrompt(monitor: Monitor, event: Finished): string {
  const outcome = [event.status, event.exitCode === undefined ? undefined : `exit ${event.exitCode}`, event.reason, event.error]
    .filter(Boolean)
    .join(", ");
  return `Monitor ${monitor.id} (${monitor.label}) finished: ${outcome || "done"}. Read its output with MonitorList and continue the task.`;
}

/**
 * Keeps an auto-exiting subagent open while monitors it started are running. Exiting would stop
 * their process groups and drop the build, test, or review the worker was waiting on.
 */
export default function monitorHold(pi: ExtensionAPI, deps: MonitorHoldDeps = defaultDeps): void {
  const running = new Map<string, Monitor>();
  const announced = new Set<string>();
  let held = false;
  let ctx: ExtensionContext | undefined;

  const prompt = (text: string, onSent?: () => void): void => {
    deps.setTimeout(() => {
      if (!ctx?.isIdle()) return;
      pi.sendUserMessage(text);
      onSent?.();
    }, PROMPT_DELAY_MS);
  };

  pi.events.on("monitor:started", (data) => {
    const event = data as { monitorId?: string; description?: string; command?: string } | undefined;
    if (!event?.monitorId) return;
    running.set(event.monitorId, { id: event.monitorId, label: event.description || event.command || "monitor" });
  });

  pi.events.on("monitor:finished", (data) => {
    const event = data as Finished | undefined;
    const monitor = event?.monitorId ? running.get(event.monitorId) : undefined;
    if (!monitor || !event) return;
    running.delete(monitor.id);
    announced.delete(monitor.id);
    if (!held) return;
    if (running.size === 0) held = false;
    prompt(finishedPrompt(monitor, event));
  });

  // Answered synchronously, so the hold does not depend on which agent_settled handler runs first.
  pi.events.on(EXIT_HOLD_CHANNEL, (data) => {
    const probe = data as { hold?: boolean } | undefined;
    if (!probe || running.size === 0) return;
    probe.hold = true;
    held = true;
    const fresh = [...running.values()].filter((monitor) => !announced.has(monitor.id));
    if (fresh.length === 0) return;
    // Marked only once sent: a prompt dropped because another wake started a turn is retried at the next hold.
    prompt(heldPrompt([...running.values()]), () => {
      for (const monitor of fresh) announced.add(monitor.id);
    });
  });

  pi.on("session_start", (_event, context) => {
    ctx = context;
  });

  pi.on("session_shutdown", () => {
    running.clear();
    announced.clear();
    held = false;
    ctx = undefined;
  });
}
