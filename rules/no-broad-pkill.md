---
description: "Agents stop only the processes they started"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*(?:pkill|killall)\b'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
blocks:
  - pkill -f chrome-154
  - killall node
  - sudo pkill -9 -f vite
allows:
  - grep -l no-broad-pkill rules/*.md
  - kill 4242
  - agent-browser --session mine close
  - grep -n "pkill -f chrome" MEMORY.md
---

Do not use `pkill` or `killall`: a name or `-f` pattern also matches processes that other workers and the user started, such as their headless Chromes and dev servers.

Stop only what you started: `kill <pid>` with the PID you recorded, `MonitorStop` for a monitor, or `agent-browser --session <name> close` for your browser session.
