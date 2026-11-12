---
description: "Agents list processes by name, not by full command line"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*(?:ps(?=\s)[^\n;&|]*(\b(command|args|cmd)\b|\s-[a-zA-Z]*f\b|\s[a-z]*x\b)|pgrep(?=\s)(?=[^\n;&|]*\s-[a-zA-Z]*f)(?=[^\n;&|]*\s-[a-zA-Z]*[la]))'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
blocks:
  - ps -Ao pid,pcpu,rss,etime,command
  - ps aux | grep dotnet
  - ps -ef | grep efcpt
  - sudo ps aux
  - pgrep -fl "cypress|vite" | head
  - pgrep -f vitest -l
  - pgrep -af node
allows:
  - grep -n "ps aux" notes.md
  - ps -Ao pid,pcpu,rss,etime,comm
  - ps -p 4242 -o pid,ppid,comm
  - pgrep -x node
  - pgrep -f vitest
  - pgrep -l node
---

Full process command lines carry secrets: tools such as efcpt, dotnet, and sqlcmd take connection strings with passwords as arguments, and one listing printed a database password into the model-visible output. `pgrep -fl` (and `-af`) prints the same full command lines and leaked API tokens twice.

List processes with the `comm` column, as in `ps -Ao pid,pcpu,rss,etime,comm`, and look up one known PID with `ps -p <pid> -o pid,ppid,comm`. `pgrep -f pattern` (PIDs only) and `pgrep -l name` stay allowed.
