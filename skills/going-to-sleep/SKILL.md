---
name: going-to-sleep
description: Use when the user is going to rest or sleep and leaves a last round of work (睡前最後一輪, 我要睡了, 準備休息, 做完就讓電腦睡), or says they are up again (我起床了, 我醒了, 早安).
---

# Going to sleep

The user is gone until morning: finish the last round on your own, then put the Mac to sleep. Entering this round is the request to sleep; skip sleep only when the user says not to (不要休眠, 電腦不要睡).

1. **Record the mandate** in the daily memory log: the work to finish, what may be merged, pushed, or deployed, and that the Mac sleeps after (or that the user said not to). Later wakes act on that entry.
2. **Tell the other sessions** the user is resting, once each, skipping yourself; a `subagent-chat-*` name can be a main session, so do not filter by name:
   `cli=~/.pi/agent/npm/node_modules/pi-intercom/cli.mjs; node $cli list --json | jq -r --arg me "$PI_SESSION_ID" '.sessions[] | select(.id != $me) | .id' | while read -r id; do node $cli send --to "$id" --text "<message>"; done`
   Ask them to reach a safe stopping point and keep user decisions for the morning, and to leave every command that can open a password, keychain, certificate, or Touch ID dialog for the morning (AGENTS.md, Work).
   Also make every polling watch call its CLI at most once a minute.
3. **Turn on auto mode** while the user is still here: hand `/boss auto on` through `robot_hand` (kind `pi`) as the last thing the user answers, or have them tell the head tower 「我要睡了」. Straw Boss then refuses every new wait and parks the tower cards for the morning. When the user declines or Straw Boss is not running, log it and go on.
4. **Make sure a wait watchdog runs, then arm the runbook watches.** The session that handles the sleep instruction owns the watchdog: confirm one is running (`LoopList` here, or a watchdog loop id another session logged in today's daily log for this sleep), else arm it with `LoopCreate`, and log its id in the daily log. The watchdog recurs about every 15 minutes; it answers a session waiting on a question or a tower card from the mandate and that session's own recommendation, nudges an idle main with work left only when the mandate gives work, and checks output (new merge requests, commits, landed trains) beyond pane activity. Then arm every watch the projects' runbooks name for unattended work (for moldplan-center's agent tower: the train handoff and output watches in `docs/runbooks/agent-tower.md`) and log their ids.
   A session without `LoopCreate` (a tower, for one) that receives a sleep instruction says so in its reply and hands the arming to a main session that has the tools, naming the mandate, and confirms the arming in the daily log.
5. **Set a safety deadline** with a one-shot `LoopCreate` (about two hours) that pushes what is verified and sleeps the Mac, so a stuck worker cannot keep it awake all night.
6. **Finish the round without the user** through the `anchorloop` autonomous-run playbook, with no `ask_user_question`, `robot_hand`, or `secret_drop`. Work that still cannot be verified stays on its local branch and goes into the daily log. Push only what the mandate covers; work the deadline cuts short ends through the `pause` playbook.
7. **Check for an open system dialog**: run `pgrep -lx SecurityAgent`. A running `SecurityAgent` means a password, keychain, or certificate dialog holds the keyboard. If the Mac sleeps with it open, the keyboard and Finder stop working after wake, and only a forced shutdown recovers them (2026-11-13). When it runs, the Mac stays awake: find the session that ran the command (its last commands near the dialog's start in `log show --predicate 'process == "WindowServer" AND eventMessage CONTAINS "SecurityAgent"' --last 12h`), stop that command, and put the dialog first on the morning list. Leave the Mac awake, with its screen locked, until the user answers the dialog.
8. **Sleep**: broadcast that the Mac is going to sleep, wait up to five minutes for a session that must stop something first, delete the deadline loop, stop any `caffeinate` you started, run the step 7 check again, then run `pmset sleepnow`.

**Complete when:** the mandate is done or logged as left over, and the Mac is asleep, unless the user said not to sleep it.

## Waking up

1. **End auto mode** if it is on: hand `/boss auto off` through `robot_hand` (kind `pi`), or the user tells the head tower 「我起床了」; its return list (parked waits, what was refused, what towers decided) joins the morning list.
2. **Wake the other sessions** with the same broadcast: the user is back, so resume interrupted work through the `anchorloop` pickup playbook, recheck monitors and services the sleep paused (`MonitorList`, `LoopList`; event loops and monitors do not survive a session recovery, so recreate every watch step 4 logged that is gone and still needed), and bring held decisions to the user.
3. **Present the morning list** from the daily log: what landed, what is left over, and what needs the user. List any system dialog found at step 7 first.
4. **Hand over cleanup** the tools refused (worktrees, panes, processes) as one command through `robot_hand`, after confirming each target is pushed or no longer needed.
