---
description: "Agents never print the shell environment"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*(?:env(?:\s+(?:-u\s+\S+|-[a-zA-Z]+|[A-Za-z_][A-Za-z0-9_]*=(?:\$\([^)\n]*\)|"[^"\n]*"|''[^''\n]*''|[^\s;&|)]*)|\d?>\S+))*|printenv|export\s+-p|declare\s+-[a-zA-Z]*x[a-zA-Z]*|set)\s*(?:$|[\n;&)]|\|(?!\s*cut\s+-d\s*[''"]?=[''"]?\s*-f\s*1\b))'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
lesson: "printed its shell environment"
blocks:
  - env
  - env | grep -E 'PI_|HERDR'
  - env | grep -i token
  - env -u STRAW_BOSS_OWNER X=$(mktemp -d /tmp/sbX.XXXX); echo $X
  - cd repo && env -u HOME 2>/dev/null; echo HOME=$HOME
  - printenv
  - printenv | sort
  - export -p
  - declare -px
  - set | grep PATH
allows:
  - env -u STRAW_BOSS_OWNER HOME=/tmp/h node --test tests/a.test.ts
  - env | cut -d= -f1 | grep -E '^(PI_|HERDR)'
  - printenv HOME
  - set -euo pipefail
  - /usr/bin/env node script.mjs
  - envsubst < a.tmpl > a.conf
  - grep -n "env | grep" notes.md
---

Never print the environment: it holds API tokens (GitLab, Linear, Gemini, TypeSafe, MCP), and tool output goes into the session log on disk and to the model provider. Between 2026-09 and 2026-11 seven sessions leaked tokens this way: bare `env` and `env -u VAR X=...` with no command (env with no command prints everything), `env | grep -E 'PI_|HERDR'` (`PI_` matches every `*_API_KEY`), and `pgrep -fl` on a process holding a token in its arguments.

To see which variables are set, print names only: `env | cut -d= -f1 | grep PI_`. To check one, test it without printing it: `[ -n "${GITLAB_TOKEN+x}" ] && echo set`. To run a command without a variable, give `env` the command: `env -u VAR cmd args`.
