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

### Make your own overlay

1. Create a private repository, for example `~/projects/my-agent-root`, laid out like this (every part is optional):

   ```text
   my-agent-root/
   ├── skills/
   │   └── my-skill/SKILL.md      # linked into ~/.agents/skills/my-skill
   ├── pi/AGENTS.append.md        # appended to ~/.pi/agent/AGENTS.md
   └── overlay.json               # optional pi package plugins
   ```

2. Put personal instructions in `pi/AGENTS.append.md` as ordinary Markdown sections:

   ```markdown
   ## Language

   Communicate with the user in Traditional Chinese.
   ```

3. Declare plugins, if any, in `overlay.json`. `path` is relative to the overlay, and the environment variable named in `variable` overrides it. A plugin whose checkout is missing is skipped with a message.

   ```json
   {"plugins": {"my_plugin": {"name": "my-plugin", "variable": "PI_MY_PLUGIN_ROOT", "path": "../my-plugin"}}}
   ```

4. Install with the overlay once:

   ```bash
   bash ~/projects/weihung-basic-agent/scripts/install.sh --overlay ~/projects/my-agent-root
   ```

   The install records the overlay, so later runs without `--overlay`, including the daily auto-update, keep it. `--no-overlay` drops it, and `uninstall.sh` removes its links and plugins too.

5. Optionally give the overlay its own `scripts/install.sh` that calls this repository's installer with `--overlay "$OVERLAY_ROOT" "$@"`, so one command installs both.

The installer does not pull this repository: run `git pull` here before re-installing to pick up upstream changes.

### What an overlay cannot change

An overlay adds; it does not replace. A skill name that exists in both repositories stops the install. Rules (`rules/`), role overrides (`agents/`), model routing (`pi/herdr-agents-models.json`), extensions (`pi/extensions/`), and the base text of `pi/AGENTS.md.in` come only from this repository. To change those, fork it and point your overlay's installer at the fork.

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
