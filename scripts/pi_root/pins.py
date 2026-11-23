"""Every pinned package source; `scripts/pi-pins.py` rewrites the versions in this file, so it imports nothing."""

BRIDGE_SOURCE = "git:github.com/wayne930242/pi-claude-bridge@96bab40077a04e7a589f91dc945af2698cdd5498"
QUOTAS_SOURCE = "npm:@latentminds/pi-quotas@0.5.0"
CLAUDE_RULES_SOURCE = "npm:pi-code@1.10.2"
# Fork pin of giuseppecrj/pi-herdr-agents: upstream main (v3.12.1, engine moved into @nubl/maestro) with its maestro
# dependency pinned to the wayne930242/maestro fork (branch weihung-integration on v0.1.2), which carries the
# solutionSpace change of closed PR #87, grouped-workspace placement (in the herdr fork itself), the macOS process-identity and cancel-settle
# fixes, the complex-coding task category, managed worktrees seeding the source's installed project .pi/npm and .pi/git, and the fork-only exit hold that pi/extensions/quota-resume.ts and monitor-hold.ts use, and a routing guideline that names
# solutionSpace as a reason to omit thinking on a task: launch (branch weihung/v3-integration). An engine change goes to the
# maestro fork, rebuilt dist/ committed (`npm run check:dist`), then the herdr fork's package.json pin, then this pin.
# Once upstream releases what this setup needs, return to the npm release: set this to npm:pi-herdr-agents@<version>, drop the PINNED_GIT
# entry and both FORKS entries (pi-herdr-agents, maestro) in scripts/pi-pins.py, and move "npm:pi-herdr-agents" out of RETIRED_SOURCES.
HERDR_AGENTS_SOURCE = "git:github.com/wayne930242/pi-herdr-agents@8e11e85377a8fc2e70a0c63895e578fb4ca80ce0"
# The npm release again since 0.15.0, which ships the fork's only change (PR #153, consolidated into #162): pi's system
# prompt goes in the first user turn, since on consumer endpoints a prompt in systemInstruction draws a false 429.
ANTIGRAVITY_SOURCE = "npm:pi-antigravity@0.15.0"
# Every other revision of a pinned git package, including an unpinned spec, is retired for the current pin.
PINNED_GIT = {
    BRIDGE_SOURCE: ("git:github.com/wayne930242/pi-claude-bridge@",),
    HERDR_AGENTS_SOURCE: ("git:github.com/wayne930242/pi-herdr-agents",),
}
# Versioned specs keep every machine on the same release; `pi update` skips them, so bump them here.
# Catppuccin Mocha with only official palette colors, matching Herdr, Ghostty, and SketchyBar; the filter loads Mocha alone.
THEME_PACKAGE = {"source": "npm:@sherif-fanous/pi-catppuccin@0.3.0", "themes": ["themes/catppuccin-mocha.json"]}
# Registry packages this setup installed before and now drops; install removes them from settings.
# pi-curated-themes shipped a catppuccin-mocha with off-palette accents; pi-secret-drop is now part of pi-robot-hand;
# the npm pi-herdr-agents release is replaced by the fork pin above, and pi must never load both; the pi-antigravity fork pin
# gave way to the npm release once upstream shipped its change.
# Straw Boss on pi moved from the straw-boss git repository to the pi-straw-boss npm package; pi-web-access is no longer used;
# pi-herdr-doc-review gave way to pi-better-show, which registers the same show_doc and so must never load beside it;
# pi-ask-user gave way to rpiv-ask-user-question, whose answer channel lets pi-straw-boss answer from the browser.
RETIRED_SOURCES = ("git:github.com/wayne930242/pi-antigravity", "npm:pi-herdr-doc-review", "npm:@victor-software-house/pi-curated-themes", "npm:pi-secret-drop", "npm:pi-herdr-agents",
                   "git:github.com/wayne930242/straw-boss", "npm:pi-web-access", "npm:pi-ask-user",
                   "git:github.com/wayne930242/pi-quotas",
                   # It kept a full gzip copy of the session on every checkpoint with no retention: 192 GB in a month.
                   "npm:@moyai/pi-session-hoarder",
                   # aaaav before 1.0 was installed from git; a machine whose state never recorded that install still sheds it.
                   "git:github.com/wayne930242/aaaav",
                   # pi-aaaav was renamed pi-anchorloop at 2.0.0.
                   "npm:pi-aaaav",
                   # Phoenix traces saw little use; the package and its local Phoenix server were retired.
                   "npm:pi-phoenix-otel",
                   # The pi-lens fork pin gave way to the npm release once upstream shipped its change.
                   "git:github.com/wayne930242/pi-lens",
                   # pi-lens ran diagnostics and language servers after every edit and cost too much CPU and memory.
                   "npm:pi-lens",
                   # pi-straw-boss ships the roles (its roles/ pack, from 0.79.0); /plan and the plan skill left with it.
                   "npm:pi-herdr-roles",
                   # The agent-desktop CLI (AGENT_DESKTOP) took over desktop app control; its tools no longer sit in every prompt.
                   "npm:@injaneity/pi-computer-use")
# pi-code loads only claude-rules.ts, which reads each project's .claude/rules as Claude Code does;
# its other extensions duplicate the todo, MCP, subagent, and web packages below.
CLAUDE_RULES_PACKAGE = {"source": CLAUDE_RULES_SOURCE, "extensions": ["extensions/claude-rules.ts"]}
PACKAGES = [
    BRIDGE_SOURCE,
    HERDR_AGENTS_SOURCE,
    "npm:pi-mcp-adapter@7.0.1",
    "npm:pi-intercom@0.18.1",
    "npm:@juicesharp/rpiv-ask-user-question@2.15.0",
    "npm:@juicesharp/rpiv-todo@2.15.0",
    THEME_PACKAGE,
    "npm:pi-open-tui@0.4.7",
    QUOTAS_SOURCE,
    "npm:pi-jev-compaction@1.0.0",
    # prose_watch: an AI-tone check (Jev) on the prose files a writing task arms.
    "npm:pi-prose-watch@0.1.2",
    "npm:cc-safety-net@2.8.2",
    "npm:pi-codex-image-gen@0.3.2",
    "npm:pi-robot-hand@0.8.1",
    "npm:pi-auto-tab-name@0.2.0",
    # show_doc: documents in the browser, answers back as messages; it replaced pi-herdr-doc-review (same tool name).
    "npm:pi-better-show@0.7.2",
    # Straw Boss coordination in Herdr: opt-in main agents per tab, an on-demand tower per workspace, scoped broadcast.
    "npm:pi-straw-boss@0.84.0",
    "npm:@pify/memory@0.14.1",
    "npm:pi-loop-monitor@0.2.8",
    # /doctor: profiles main-thread stalls and asks long, strained mains to rotate through a handoff file.
    "npm:pi-session-doctor@0.1.0",
    "npm:@narumitw/pi-goal@0.55.4",
    # Antigravity (agy) Google login: /login antigravity, plus the google_search and generate_image tools.
    ANTIGRAVITY_SOURCE,
    CLAUDE_RULES_PACKAGE,
]
# The Herdr plugins in pi-straw-boss, each installed with `herdr plugin install` at its tag: plugin id, repository path, tag,
# and the state key that records whether the user had it before install. They change less often than the pi package:
# scripts/pi-pins.py moves a tag to the newest release only when that folder differs there. herdr-plugin is the sidebar's net view (prefix+alt+n); herdr-reaper closes the
# panes agents leave in worktree workspaces, removes their clean checkouts, and keeps pinned workspaces (prefix+P).
HERDR_PLUGINS = (
    ("wayne930242.straw-boss", "wayne930242/pi-straw-boss/herdr-plugin", "v0.50.0", "straw_boss_plugin_preinstalled"),
    ("wayne930242.straw-boss-reaper", "wayne930242/pi-straw-boss/herdr-reaper", "v0.80.13", "reaper_plugin_preinstalled"),
)
# The Playwriter CLI drives the user's own Chrome through its extension; playwriter-relay.ts starts its relay.
PLAYWRITER = "playwriter@0.12.0"
# The agent-desktop CLI controls desktop apps through the accessibility tree (AX, UIA, AT-SPI). Ref actions are headless
# by default: no pointer move, no focus change. skills/agent-desktop points agents at the guides the binary carries.
AGENT_DESKTOP = "agent-desktop@1.3.1"
# team-toon-tack: the ttt CLI, the managing-linear-tasks skill and the /ttt-* prompts (resources.py). Pinned like every other
# package, since an unattended computer runs it in the account that holds a person's Linear key.
TEAM_TOON_TACK = "team-toon-tack@3.17.0"
# The statechart skill (MIT, Lauren Tan's pstack in cursor/plugins) and the TLC jar it runs, both fetched at a fixed
# revision or checksum (scripts/pi_root/resources.py). The skill's own runner would install Java and the jar through mise;
# the installer fetches the jar itself and the installed wrapper points the runner at it, so mise is not needed.
# Bump by hand: set `rev` to a commit of the repository, and `jar_url` plus `jar_sha256` to a tla2tools release.
STATECHART = {
    "git": "https://github.com/cursor/plugins.git",
    "rev": "a5539b15a3d56e04992565aafee2b37051329ce3",
    "path": "harness/pstack/claude-code/skills/statechart",
    "jar_url": "https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar",
    "jar_sha256": "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88",
}
# The unattended install profile (scripts/pi_root/unattended.py) leaves these out: packages and skills that need a person at the
# computer, a desktop, or an interactive login. Names carry no version, so a pin bump never touches them.
UNATTENDED_DROPS = (
    "npm:cc-safety-net",
    "npm:pi-codex-image-gen",
    "npm:pi-robot-hand",
    "npm:pi-antigravity",
    "npm:pi-open-tui",
    "npm:pi-better-show",
    "npm:pi-auto-tab-name",
    "npm:pi-prose-watch",
    # nobody answers a question on an unattended computer
    "npm:@juicesharp/rpiv-ask-user-question",
)
# statechart needs a Java runtime, which the box has not been checked for; add it back once it has.
# agent-desktop needs a desktop session, which the box's agents never drive.
UNATTENDED_DROPPED_SKILLS = ("agent-desktop", "going-to-sleep", "recording-with-obs", "statechart")
# anchorloop, the workflow skills and extensions; PI_ANCHORLOOP_ROOT swaps in a checkout for testing.
ANCHORLOOP_PACKAGE = "npm:pi-anchorloop@3.0.0"
