---
description: "Agents do not use git stash"
condition: '(?:^|[\n;(`]|(?<!\\)[|&]|\b(?:then|do|else)\s)\s*(?:(?:sudo|nohup|xargs|time|timeout\s+\S+)\s+)*git(?:\s+-C\s+\S+)*\s+stash\b(?!\s+(?:list|pop)\b)'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
blocks:
  - git stash -q
  - git stash push -m prove-red
  - git stash drop stash@{0}
  - cd repo && git stash
  - git -C ~/projects/x stash push
allows:
  - git stash list
  - git stash pop
  - cd repo && git stash list | head -3
  - grep -n "git stash -q" MEMORY.md
  - grep -n "pkill -f chrome\|git stash 是" MEMORY.md
  - git show HEAD:src/a.py > src/a.py
  - grep -n stash notes.md
---

Do not create or drop stash entries with `git stash`: a stash entry outlives the run, and Safety Net blocks `git stash drop`, so it stays behind for the user to clean up.

To prove a test fails without a change, copy the changed file to `/tmp` and restore it afterwards, or run `git show HEAD:<path> > <path>` and put your version back. To set work aside, commit it on a branch. `git stash list` and `git stash pop` stay allowed: one only reads, the other brings an entry back and removes it.
