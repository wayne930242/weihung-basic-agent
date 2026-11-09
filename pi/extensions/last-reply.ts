/**
 * Footer stamp of when the agent last replied, so a glance tells how long the session has sat idle.
 *
 * When a run settles, the footer shows `last reply MM/DD HH:MM` in local time. A resumed session
 * takes the stamp from the last assistant message on its branch.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const STATUS_KEY = "last-reply";

export function formatStamp(time: Date): string {
	const pad = (n: number): string => String(n).padStart(2, "0");
	return `last reply ${pad(time.getMonth() + 1)}/${pad(time.getDate())} ${pad(time.getHours())}:${pad(time.getMinutes())}`;
}

function lastAssistantTime(ctx: ExtensionContext): Date | undefined {
	const branch = ctx.sessionManager.getBranch();
	for (let i = branch.length - 1; i >= 0; i--) {
		const entry = branch[i] as { type: string; message?: { role?: string; timestamp?: number } };
		if (entry.type === "message" && entry.message?.role === "assistant" && entry.message.timestamp) {
			return new Date(entry.message.timestamp);
		}
	}
	return undefined;
}

export default function lastReply(pi: ExtensionAPI): void {
	pi.on("session_start", (_event, ctx) => {
		if (!ctx.hasUI) return;
		const time = lastAssistantTime(ctx);
		if (time) ctx.ui.setStatus(STATUS_KEY, formatStamp(time));
	});
	pi.on("agent_settled", (_event, ctx) => {
		if (ctx.hasUI) ctx.ui.setStatus(STATUS_KEY, formatStamp(new Date()));
	});
}
