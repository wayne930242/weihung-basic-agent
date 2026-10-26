"""Every pinned package source; `scripts/pi-pins.py` rewrites the versions in this file, so it imports nothing."""

BRIDGE_SOURCE = "git:github.com/wayne930242/pi-claude-bridge@cf8c6e1035681bc12c2499c0a6c2edd273a444eb"
QUOTAS_SOURCE = "npm:@latentminds/pi-quotas@0.5.0"
CLAUDE_RULES_SOURCE = "npm:pi-code@1.5.2"
# Fork pin of giuseppecrj/pi-herdr-agents: upstream v3.3.1 plus PRs #84, #95, and #99, the solutionSpace change of
# closed PR #87, the macOS process-identity fixes, and the fork-only exit hold that pi/extensions/quota-resume.ts and
# monitor-hold.ts use (branch weihung/v3-integration).
# Once upstream releases what this setup needs, return to the npm release: set this to npm:pi-herdr-agents@<version>, drop the PINNED_GIT
# entry and the FORK_BRANCHES entry in scripts/pi-pins.py, and move "npm:pi-herdr-agents" out of RETIRED_SOURCES.
HERDR_AGENTS_SOURCE = "git:github.com/wayne930242/pi-herdr-agents@19ba73e7f96c73a028d8657e6291cdc5a3bf830e"
# The pi-herdr-agents v3 role pack: planner, /plan, and /skill:plan. Its orchestrate skill is filtered out because
# skills/orchestrate owns our trimmed version. Pinned by hand (MANUAL_PINS) since a 0.x bump can change the planner.
HERDR_ROLES_SOURCE = "npm:pi-herdr-roles@0.1.0"
HERDR_ROLES_PACKAGE = {"source": HERDR_ROLES_SOURCE, "skills": ["!orchestrate"]}
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
# the npm pi-herdr-agents release is replaced by the fork pin above, and pi must never load both.
# Straw Boss on pi moved from the straw-boss git repository to the pi-straw-boss npm package; pi-web-access is no longer used;
# pi-ask-user gave way to rpiv-ask-user-question, whose answer channel lets pi-straw-boss answer from the browser.
RETIRED_SOURCES = ("npm:@victor-software-house/pi-curated-themes", "npm:pi-secret-drop", "npm:pi-herdr-agents",
                   "git:github.com/wayne930242/straw-boss", "npm:pi-web-access", "npm:pi-ask-user",
                   "git:github.com/wayne930242/pi-quotas",
                   # It kept a full gzip copy of the session on every checkpoint with no retention: 192 GB in a month.
                   "npm:@moyai/pi-session-hoarder",
                   # aaaav before 1.0 was installed from git; a machine whose state never recorded that install still sheds it.
                   "git:github.com/wayne930242/aaaav")
# pi-code loads only claude-rules.ts, which reads each project's .claude/rules as Claude Code does;
# its other extensions duplicate the todo, MCP, subagent, and web packages below.
CLAUDE_RULES_PACKAGE = {"source": CLAUDE_RULES_SOURCE, "extensions": ["extensions/claude-rules.ts"]}
PACKAGES = [
    BRIDGE_SOURCE,
    HERDR_AGENTS_SOURCE,
    HERDR_ROLES_PACKAGE,
    "npm:pi-mcp-adapter@5.3.2",
    "npm:pi-intercom@0.17.1",
    "npm:@juicesharp/rpiv-ask-user-question@2.13.9",
    "npm:@juicesharp/rpiv-todo@2.13.9",
    THEME_PACKAGE,
    "npm:pi-open-tui@0.3.11",
    "npm:pi-lens@4.4.3",
    QUOTAS_SOURCE,
    "npm:pi-jev-compaction@1.0.0",
    # prose_watch: an AI-tone check (Jev) on the prose files a writing task arms.
    "npm:pi-prose-watch@0.1.2",
    "npm:cc-safety-net@2.6.13",
    "npm:pi-codex-image-gen@0.2.0",
    "npm:pi-robot-hand@0.3.2",
    "npm:pi-auto-tab-name@0.2.0",
    "npm:pi-herdr-doc-review@0.7.0",
    # Straw Boss coordination in Herdr: opt-in main agents per tab, an on-demand tower per workspace, scoped broadcast.
    "npm:pi-straw-boss@0.42.7",
    "npm:@pify/memory@0.14.0",
    "npm:pi-loop-monitor@0.2.8",
    "npm:@narumitw/pi-goal@0.54.12",
    "npm:pi-phoenix-otel@0.2.0",
    # Antigravity (agy) Google login: /login antigravity, plus the google_search and generate_image tools.
    "npm:pi-antigravity@0.10.0",
    # Desktop app control through Accessibility (UIA on Windows), kept headless by configs.COMPUTER_USE_SETTINGS.
    "npm:@injaneity/pi-computer-use@0.5.1",
    CLAUDE_RULES_PACKAGE,
]
# The Herdr plugins in pi-straw-boss, each installed with `herdr plugin install` at its tag: plugin id, repository path, tag,
# and the state key that records whether the user had it before install. They change less often than the pi package:
# bump a tag when that folder changes. herdr-plugin is the sidebar's net view (prefix+alt+n); herdr-reaper closes the
# panes agents leave in worktree workspaces, removes their clean checkouts, and keeps pinned workspaces (prefix+P).
HERDR_PLUGINS = (
    ("wayne930242.straw-boss", "wayne930242/pi-straw-boss/herdr-plugin", "v0.9.4", "straw_boss_plugin_preinstalled"),
    ("wayne930242.straw-boss-reaper", "wayne930242/pi-straw-boss/herdr-reaper", "v0.39.0", "reaper_plugin_preinstalled"),
)
# The Playwriter CLI drives the user's own Chrome through its extension; playwriter-relay.ts starts its relay.
PLAYWRITER = "playwriter@0.8.0"
# thesis-toolkit launches the research-hub MCP server (literature search, open-access download, bibliography saves).
THESIS_TOOLKIT = "thesis-toolkit@0.1.3"
# aaaav, the workflow skills and extensions; PI_AAAAV_ROOT swaps in a checkout for testing.
AAAAV_PACKAGE = "npm:pi-aaaav@1.3.4"
