"""A fresh machine has neither an anchorloop checkout nor the optional plugins an overlay declares."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANCHORLOOP_PACKAGE = "npm:pi-anchorloop@2.0.0"
PINS = (ROOT / "scripts/pi_root/pins.py").read_text()


def pinned(pattern: str) -> tuple[str, ...]:
    match = re.search(pattern, PINS)
    assert match, pattern
    return match.groups()


STRAW_BOSS = pinned(r'"(npm:pi-straw-boss@[^"]+)"')[0]
# Each Herdr plugin as (id, repository path, tag).
HERDR_PLUGINS = [match[:3] for match in re.findall(r'\("(wayne930242\.[^"]+)", "([^"]+)", "([^"]+)", "([^"]+)"\)', PINS)]
assert [plugin_id for plugin_id, _, _ in HERDR_PLUGINS] == ["wayne930242.straw-boss", "wayne930242.straw-boss-reaper"], HERDR_PLUGINS
STRAW_BOSS_PLUGIN_ID, *STRAW_BOSS_PLUGIN = HERDR_PLUGINS[0]
HERDR_WEB_UI_ID = "devswha.herdr-web-ui"


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def run(script, home, env):
    return subprocess.run(["bash", str(ROOT / "scripts" / script), "--home", str(home)],
                          env=env, check=True, capture_output=True, text=True)


with tempfile.TemporaryDirectory(prefix="pi-fresh-machine-") as temporary:
    base = Path(temporary)
    home = base / "home"
    bin_dir = base / "bin"
    calls = base / "pi-calls.log"
    npm_calls = base / "npm-calls.log"
    fixture = base / "team-toon-tack"
    write(fixture / "skills/managing-linear-tasks/SKILL.md", "---\nname: managing-linear-tasks\ndescription: Test skill\n---\n")
    write(fixture / "commands/ttt-status.md", "# ttt status\n")
    write(bin_dir / "npm", """#!/usr/bin/env python3
import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['TEST_NPM_CALLS'], 'a') as log:
    log.write(' '.join(args) + '\\n')
if args[:1] == ['ls']:
    sys.exit(1)
if '--prefix' in args:
    prefix = Path(args[args.index('--prefix') + 1])
    shutil.copytree(os.environ['TEST_TTT_FIXTURE'], prefix / 'node_modules/team-toon-tack', dirs_exist_ok=True)
    cli = prefix / 'node_modules/.bin/ttt'
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text('#!/bin/sh\\n')
    cli.chmod(0o755)
""", True)
    pi_skills = base / "pi-skills"
    write(pi_skills / "brave-search/SKILL.md", "---\nname: brave-search\ndescription: Test skill\n---\n")
    subprocess.run(["git", "init", "-q", str(pi_skills)], check=True)
    subprocess.run(["git", "-C", str(pi_skills), "add", "."], check=True)
    subprocess.run(["git", "-C", str(pi_skills), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixture"], check=True)
    # An optional plugin whose `pi` calls fail must not stop the install or uninstall.
    write(bin_dir / "pi", f"#!/bin/sh\necho \"$@\" >> '{calls}'\ncase \"$*\" in */beta) exit 1;; esac\n", True)
    overlay = base / "overlay"
    write(overlay / "overlay.json", '{"plugins": {"alpha": {"name": "alpha", "variable": "PI_ALPHA_ROOT", "path": "../no-alpha"}, "beta": {"name": "beta", "variable": "PI_BETA_ROOT", "path": "../no-beta"}}}')
    herdr_calls = base / "herdr-calls"
    herdr_plugins = base / "herdr-plugins"
    # Real herdr exits 1 when asked to remove a plugin it does not have, so the installed plugins decide what
    # `plugin list` reports.
    write(bin_dir / "herdr", f"""#!/bin/sh
echo "$@" >> '{herdr_calls}'
state='{herdr_plugins}'
case "$1 $2" in
  'plugin list')
    if [ -f "$state" ]; then cat "$state"; else echo 'No plugins installed.'; fi
    ;;
  'plugin install')
    case "$3" in */herdr-reaper) id=wayne930242.straw-boss-reaper;; *) id=wayne930242.straw-boss;; esac
    echo "- $id (Straw Boss) enabled [github:$3@$5]" >> "$state"
    echo "  config: /config/$id" >> "$state"
    ;;
  'plugin uninstall')
    if grep -q -- "- $3 (" "$state" 2>/dev/null; then grep -v -e "- $3 (" -e "/config/$3$" "$state" > "$state.new"; mv "$state.new" "$state"; else echo "plugin not installed: $3" >&2; exit 1; fi
    ;;
esac
""", True)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "WEIHUNG_OVERLAY": str(overlay),
           "TEST_TTT_FIXTURE": str(fixture), "PI_SKILLS_GIT": str(pi_skills), "TEST_NPM_CALLS": str(npm_calls)}
    agent = home / ".pi/agent"

    result = run("install.sh", home, env)
    assert "alpha" in result.stderr and "skipped" in result.stderr, result.stderr
    assert not (agent / "alpha.json").exists()
    assert "beta not found" in result.stderr, result.stderr
    assert f"install {ANCHORLOOP_PACKAGE}" in calls.read_text().splitlines()
    assert ANCHORLOOP_PACKAGE in json.loads((agent / "settings.json").read_text())["packages"]
    assert f"install {STRAW_BOSS}" in calls.read_text().splitlines()
    assert STRAW_BOSS in json.loads((agent / "settings.json").read_text())["packages"]
    assert "install -g playwriter@0.8.0" in npm_calls.read_text().splitlines()
    # Each Herdr plugin is installed at its pinned tag, once: a second install finds them there.
    plugin_installs = [f"plugin install {repo} --ref {ref} --yes" for _, repo, ref in HERDR_PLUGINS]
    assert [line for line in herdr_calls.read_text().splitlines() if line.startswith("plugin ") and line != "plugin list"] == plugin_installs
    run("install.sh", home, env)
    assert all(herdr_calls.read_text().splitlines().count(line) == 1 for line in plugin_installs)
    # A plugin at another tag is replaced, and the other plugin, whose id begins with its id, stays as it is.
    reaper = next(line for line in herdr_plugins.read_text().splitlines() if "herdr-reaper@" in line)
    write(herdr_plugins, f"- {STRAW_BOSS_PLUGIN_ID} (Straw Boss) enabled [github:{STRAW_BOSS_PLUGIN[0]}@v0.0.1]\n{reaper}\n")
    logged = len(herdr_calls.read_text().splitlines())
    run("install.sh", home, env)
    assert [line for line in herdr_calls.read_text().splitlines()[logged:] if line.startswith("plugin ") and line != "plugin list"] == [
        f"plugin uninstall {STRAW_BOSS_PLUGIN_ID}", plugin_installs[0]]
    assert f"github:{STRAW_BOSS_PLUGIN[0]}@{STRAW_BOSS_PLUGIN[1]}" in herdr_plugins.read_text()
    # Uninstall removes the plugins install added.
    run("uninstall.sh", home, env)
    assert not any(plugin_id in herdr_plugins.read_text() for plugin_id, _, _ in HERDR_PLUGINS)
    run("install.sh", home, env)

    plugin = base / "plugins/beta"
    write(plugin / "package.json", "{}")
    env = {**env, "PI_BETA_ROOT": str(plugin)}
    result = run("install.sh", home, env)
    assert f"could not run pi install for {plugin.resolve()}" in result.stderr, result.stderr
    assert str(plugin.resolve()) in json.loads((agent / "settings.json").read_text())["packages"]
    result = run("uninstall.sh", home, env)
    assert f"could not run pi remove for {plugin.resolve()}" in result.stderr, result.stderr
    assert "uninstall -g playwriter" in npm_calls.read_text().splitlines()
    assert f"remove {ANCHORLOOP_PACKAGE}" in calls.read_text().splitlines()
    assert f"remove {STRAW_BOSS}" in calls.read_text().splitlines()

    # herdr web ui is retired: an earlier install that added the plugin removes it once, one the user had stays.
    marker = home / ".pi/agent/.weihung-agent-root.json"
    for preinstalled, removed in ((False, True), (True, False)):
        run("install.sh", home, env)
        write(herdr_plugins, f"- {HERDR_WEB_UI_ID} (herdr web ui) enabled\n")
        state = json.loads(marker.read_text())
        marker.write_text(json.dumps({**state, "herdr_web_ui_preinstalled": preinstalled}))
        logged = len(herdr_calls.read_text().splitlines())
        run("install.sh", home, env)
        uninstalled = f"plugin uninstall {HERDR_WEB_UI_ID}" in herdr_calls.read_text().splitlines()[logged:]
        assert uninstalled == removed, (preinstalled, uninstalled)
        assert "herdr_web_ui_preinstalled" not in json.loads(marker.read_text())
        run("uninstall.sh", home, env)
        herdr_plugins.unlink(missing_ok=True)
    print("pi fresh machine: pass")
