---
description: "A shell timeout escalates to SIGKILL so a command that ignores SIGTERM cannot outlive it"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|time)\s+)*g?timeout\s+(?:(?!-k|--kill-after|-s\s*(?:KILL|SIGKILL|9)\b|--signal=(?:KILL|SIGKILL|9)\b)(?:-s\s+\S+|-\S+)\s+)*\d+(?:\.\d+)?[smhd]?\s+\S'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
lesson: Running tests as `timeout <N> cmd` without `-k`
blocks:
  - timeout 600 npm run test:one -- tests/tower.test.ts
  - cd packages/server && timeout 120s node --test tests/a.mjs
  - gtimeout 30 pytest -q
  - timeout --preserve-status 60 bun test
allows:
  - timeout -k 10s 600 npm run test:one -- tests/tower.test.ts
  - timeout --kill-after=5s 10 npm test
  - timeout -s KILL 60 node server.js
  - npx vitest run --timeout 30000
  - curl --max-time 5 --connect-timeout 3 https://example.com
  - grep -n "timeout 600" notes.md
---

`timeout <N> cmd` sends only SIGTERM when time runs out. A command that handles SIGTERM and hangs in shutdown keeps running, and `timeout` exits 124 anyway. Four node test processes once outlived such a run for six hours, reparented to PID 1, at a machine load of 30 to 70.

Give the time limit to pi's bash tool through its `timeout` parameter, which kills the whole process tree, or escalate with `timeout -k 10s <N> cmd`. Run a command longer than a few minutes with `MonitorCreate`.
