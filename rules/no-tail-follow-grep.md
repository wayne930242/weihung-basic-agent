---
description: "Agents do not wait on a log with tail -F piped to grep"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*tail\b[^|\n]*\s-[a-zA-Z]*[fF]\b[^|\n]*\|\s*grep\b'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
blocks:
  - timeout 600 tail -F build.log | grep -m1 DONE
  - tail -f out.log | grep -q ready
  - cd logs; tail -f a.log | grep ok
allows:
  - grep -c "tail -F log | grep" notes.md
  - until grep -q DONE build.log; do sleep 2; done
  - tail -n 50 build.log | grep ERROR
---

Do not wait on a log with `tail -f`/`tail -F` piped to `grep`: after `grep` matches and exits, `tail` only dies on its next write, and a finished log is never written again, so the command hangs until its timeout.

Run the build or test in the foreground and read its output, or wait with a loop that checks the file, such as `until grep -q PATTERN log; do sleep 2; done`.
