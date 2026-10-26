---
description: "Agents stage files by name"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*git(?:\s+-C\s+\S+)*\s+add\b[^\n;&|]*\s(-A|--all|\.)(?=\s|$|[;&|])'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
blocks:
  - git add -A
  - git add --all && git commit -m wip
  - git add .
  - git -C ~/projects/x add -A
allows:
  - grep -n "git add -A" notes.md
  - git add rules/a.md scripts/b.py
  - git add ./rules/a.md
  - git add -p rules/a.md
---

Do not stage with `git add -A`, `git add --all`, or `git add .`: they pick up machine-local state such as plans, memory, scratch files, and other workers' changes.

Stage each file by name: `git add path/to/a.ts path/to/b.ts`.
