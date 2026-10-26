---
description: "A failing command piped to tail or head does not continue an && chain into a commit or release"
condition: '^(?![\s\S]*pipefail)[\s\S]*\|\s*(tail|head)\b[^|;&\n]*&&(?:[\s\S]*(?:[\n;(]|&&))?\s*(?:git(?:\s+-C\s+\S+)*\s+(?:commit|push|tag)|(?:npm|bun)\s+publish)\b'
scope: "tool:bash"
repeatMode: after-gap
repeatGap: 1
lesson: Piping a test through `| tail -1` inside an && chain
blocks:
  - python3 tests/pi_packages.py 2>&1 | tail -1 && git commit -m "chore(pi): bump pins" && git push
  - uv run pytest -q 2>&1 | tail -4 && npm publish
allows:
  - uv run pytest -q 2>&1 | tail -4 && uv run python hooks/validate_all.py .
  - set -o pipefail; uv run pytest -q 2>&1 | tail -4 && git commit -m done
  - uv run pytest -q 2>&1 | tail -4; git status --short
  - git log --oneline | head -5
  - git status -sb | head -3 && git log --oneline -3
  - npm test | tail -3 && grep -n "git commit" notes.md
---

A pipeline exits with the status of its last command, so `test | tail -1 && git commit` commits even when the test failed; a commit and push once went out over a red suite this way.

Start the command with `set -o pipefail;` so the chain stops on the failure, or end the chain at the pipe and read the output before the next step.
