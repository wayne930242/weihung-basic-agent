# weihung-basic-agent

A user-root setup for [pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) that installs standalone. One command links its skills, rules, and role overrides into your home directory, installs pi and a pinned set of pi packages, generates `~/.pi/agent/AGENTS.md`, and sets model routing for [pi-herdr-agents](https://github.com/giuseppecrj/pi-herdr-agents) in Herdr.

## Install

Prerequisites: Node.js with npm, Python 3, Git, [Herdr](https://herdr.dev), and Claude Code logged in (Claude models reach pi through `pi-claude-bridge`, which uses its login).

```bash
git clone https://github.com/wayne930242/weihung-basic-agent ~/projects/weihung-basic-agent
cd ~/projects/weihung-basic-agent
bash scripts/install.sh
```

Then start `pi` inside Herdr and run `/login` for the providers you use.

- `--skip-external` writes configuration only: no npm, pi package, Herdr, or network installs.
- `--home PATH` installs into another home directory, for a throwaway smoke test.
- `--force` backs up conflicting targets to `~/.local/state/weihung-agent-root/backups/<timestamp>/` before replacing them; without it a conflict stops the install.
- `bash scripts/uninstall.sh` removes what the install added and restores what it backed up.

The installer never overwrites a file you own silently, and it is idempotent: re-run it after pulling changes.

## What you get

- **Skills** in `skills/`: `orchestrate`, `reflecting-to-root`, `maintaining-pi-setup`, `publishing-pi-extensions`, `recording-with-obs`, `going-to-sleep`.
- **Rules** in `rules/`: conventions for Git, deployment, dependencies, architecture, UI, Go, Python, shell, TypeScript, and Markdown, plus stream rules that block known command mistakes.
- **Role overrides** in `agents/` for the `pi-herdr-agents` roles, and **model routing** in `pi/herdr-agents-models.json`.
- **Extensions** in `pi/extensions/`: auto thinking level, idle compaction, quota resume, batch guard, monitor hold, and the Playwriter relay.
- **Instructions**: `pi/AGENTS.md.in` becomes `~/.pi/agent/AGENTS.md`.

## Layering your own material

`bash scripts/install.sh --overlay PATH` layers a second checkout over this one: its `skills/` link beside ours, its `pi/AGENTS.append.md` is appended to the generated `AGENTS.md`, and its `overlay.json` can declare optional plugins. That keeps personal or company material in a private repository while this one stays public.

## Tests

```bash
bash tests/install.sh
bash tests/uninstall.sh
for test in tests/pi_*.py; do python3 "$test"; done   # tests/pi_fresh_machine.py is slow
for test in tests/*.mjs; do node --experimental-strip-types --test "$test"; done
```

See [docs/reference.md](docs/reference.md) for the full list of packages, settings, and links, and [AGENTS.md](AGENTS.md) for how the repository is organised.

## License

MIT
