"""Files and links pi cannot install as packages: team-toon-tack, pi-skills and the statechart skill."""

import hashlib
import json
import os
import shlex
import shutil
from datetime import datetime
from pathlib import Path

from . import external
from .context import State
from .jsonfile import write_json
from .paths import MARKER, PI_SKILLS_CLONE, PI_SKILLS_GIT, STATECHART_PIN_VARIABLE, STATECHART_ROOT, TTT_PREFIX
from .pins import STATECHART, TEAM_TOON_TACK

PI_SKILLS_LINK = Path(".pi/agent/skills/pi-skills")
STATECHART_LINK = Path(".agents/skills/statechart")

# The statechart skill's own runner finds TLC through mise unless TLA2TOOLS (a tla2tools.jar) and JAVA (Java 11 or later) are set.
# This wrapper replaces the skill's scripts/statechart in the installed folder: it sets both and runs the upstream script.
STATECHART_WRAPPER = r"""#!/bin/sh
# Installed by weihung-agent-root; not part of the upstream skill. Runs the pinned statechart with the pinned TLC jar
# and a Java 11 or later runtime, so the skill never installs either through mise. JAVA and TLA2TOOLS in the
# environment win.
java_major() {
  "$1" -version 2>&1 | sed -n '1s/.*version "\([0-9][0-9]*\).*/\1/p'
}
if [ -z "${JAVA:-}" ]; then
  for candidate in "${JAVA_HOME:-/nonexistent}/bin/java" java /opt/homebrew/opt/openjdk/bin/java /opt/homebrew/opt/openjdk@*/bin/java \
      /usr/local/opt/openjdk/bin/java /usr/local/opt/openjdk@*/bin/java; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    major=$(java_major "$candidate")
    if [ -n "$major" ] && [ "$major" -ge 11 ]; then
      JAVA=$(command -v "$candidate")
      break
    fi
  done
fi
if [ -z "${JAVA:-}" ]; then
  echo "statechart needs Java 11 or later: install one (brew install openjdk) or set JAVA to a java binary." >&2
  exit 127
fi
export JAVA
export TLA2TOOLS="${TLA2TOOLS:-%(jar)s}"
exec %(entry)s "$@"
"""


def managed_resource(home: Path, state: State, destination: Path, source: Path | bytes, force: bool = False, link: bool = False) -> None:
    """Install a file or link while retaining a user-owned predecessor; a link takes a path, a file its bytes."""
    wanted = str(source) if isinstance(source, Path) else hashlib.sha256(source).hexdigest()
    key = str(destination.relative_to(home))
    records = state.setdefault("ported_resources", {})
    record = records.get(key)
    if destination.exists() or destination.is_symlink():
        current = (destination.readlink().as_posix() if destination.is_symlink() else
                   hashlib.sha256(destination.read_bytes()).hexdigest() if destination.is_file() else None)
        if record and current == record.get("installed"):
            destination.unlink()
        elif not record and current == wanted and (destination.is_symlink() if link else destination.is_file()):
            return
        else:
            if not force:
                raise ValueError(f"{destination} exists; use --force to back it up")
            backup = home / ".local/state/weihung-agent-root/backups" / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S") / key
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(destination, backup)
            record = {**(record or {}), "backup": str(backup)}
            # Record the backup before the next step can fail, so uninstall still restores it.
            records[key] = record
            write_json(home / MARKER, state)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, Path):
        destination.symlink_to(source)
    else:
        destination.write_bytes(source)
    records[key] = {**(record or {}), "installed": wanted, "link": link}
    write_json(home / MARKER, state)


def install_ported_resources(home: Path, state: State, force: bool) -> None:
    install_ttt(home, state, force)
    install_pi_skills(home, state, force)
    install_statechart(home, state, force)


def install_ttt(home: Path, state: State, force: bool) -> None:
    agent_dir = home / ".pi/agent"
    prefix = home / TTT_PREFIX
    external.run(["npm", "install", "--prefix", str(prefix), "--no-save", "--no-package-lock", TEAM_TOON_TACK], home)
    ttt_root = prefix / "node_modules/team-toon-tack"
    if not (ttt_root / "skills/managing-linear-tasks/SKILL.md").is_file():
        raise ValueError(f"team-toon-tack package is missing: {ttt_root}")
    state["ttt_prefix"] = str(prefix)
    write_json(home / MARKER, state)

    managed_resource(home, state, agent_dir / "skills/managing-linear-tasks", ttt_root / "skills/managing-linear-tasks", force, link=True)
    for command in sorted((ttt_root / "commands").glob("ttt-*.md")):
        action = ("Create the resulting project skill under `.agents/skills/` for Pi."
                  if command.stem == "ttt-write-work-on-skill" else
                  f"Use Pi's shell tool and `{home / '.local/bin/ttt'}` for the matching CLI operation.")
        prompt = (f"---\ndescription: Run team-toon-tack {command.stem.removeprefix('ttt-')}\n"
                  f"argument-hint: '[arguments]'\n---\n"
                  f"Read and follow `{command}` for this request. Interpret its `{{{{ ... }}}}` placeholders "
                  "from these arguments: $ARGUMENTS. Translate `/ttt:*` references to Pi's `/ttt-*` templates. "
                  f"{action}\n")
        managed_resource(home, state, agent_dir / "prompts" / command.name, prompt.encode(), force)
    cli = prefix / "node_modules/.bin/ttt"
    if not cli.exists():
        raise ValueError(f"team-toon-tack CLI is missing: {cli}")
    managed_resource(home, state, home / ".local/bin/ttt", cli, force, link=True)


def install_pi_skills(home: Path, state: State, force: bool) -> None:
    clone = home / PI_SKILLS_CLONE
    if (clone / ".git").is_dir():
        external.run(["git", "-C", str(clone), "pull", "-q", "--ff-only"], home)
    else:
        external.run(["git", "clone", "-q", "--depth", "1", PI_SKILLS_GIT, str(clone)], home)
    state["pi_skills_clone"] = str(clone)
    write_json(home / MARKER, state)
    managed_resource(home, state, home / PI_SKILLS_LINK, clone, force, link=True)


def statechart_pin() -> dict[str, str]:
    """The pinned statechart source, or the keys PI_STATECHART_PIN's JSON file replaces (the installer tests point it at a fixture)."""
    override = os.environ.get(STATECHART_PIN_VARIABLE)
    return {**STATECHART, **(json.loads(Path(override).read_text()) if override else {})}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_statechart_source(home: Path, clone: Path, pin: dict[str, str]) -> None:
    """Check out only the skill's folder at the pinned revision; a clone already there is left alone."""
    if (clone / ".git").is_dir() and external.capture(["git", "-C", str(clone), "rev-parse", "HEAD"], home).strip() == pin["rev"]:
        return
    git = ["git", "-C", str(clone)]
    if not (clone / ".git").is_dir():
        clone.mkdir(parents=True, exist_ok=True)
        external.run(["git", "init", "-q", str(clone)], home)
    external.run([*git, "config", "remote.origin.url", pin["git"]], home)
    external.run([*git, "sparse-checkout", "set", "--cone", pin["path"]], home)
    external.run([*git, "fetch", "-q", "--depth", "1", "origin", pin["rev"]], home)
    external.run([*git, "checkout", "-q", "--detach", "FETCH_HEAD"], home)
    head = external.capture([*git, "rev-parse", "HEAD"], home).strip()
    if head != pin["rev"]:
        raise ValueError(f"statechart source is at {head or 'no revision'}, not the pinned {pin['rev']}: {clone}")


def fetch_tla2tools(home: Path, jar: Path, pin: dict[str, str]) -> None:
    """Download the TLC jar and keep it only when it matches the pinned checksum."""
    if jar.is_file() and sha256_file(jar) == pin["jar_sha256"]:
        return
    partial = jar.with_name(jar.name + ".part")
    jar.parent.mkdir(parents=True, exist_ok=True)
    external.run(["curl", "-fsSL", "-o", str(partial), pin["jar_url"]], home)
    found = sha256_file(partial)
    if found != pin["jar_sha256"]:
        partial.unlink()
        raise ValueError(f"{pin['jar_url']} has checksum {found}, not the pinned {pin['jar_sha256']}")
    partial.replace(jar)


def build_statechart_skill(skill: Path, source: Path, jar: Path) -> None:
    """The folder pi reads: every file of the upstream skill linked in place, except scripts/statechart, which is the wrapper."""
    if skill.exists() or skill.is_symlink():
        shutil.rmtree(skill)
    (skill / "scripts").mkdir(parents=True)
    for entry in source.iterdir():
        if entry.name != "scripts":
            (skill / entry.name).symlink_to(entry)
    for entry in (source / "scripts").iterdir():
        if entry.name != "statechart":
            (skill / "scripts" / entry.name).symlink_to(entry)
    wrapper = skill / "scripts/statechart"
    wrapper.write_text(STATECHART_WRAPPER % {"jar": jar, "entry": shlex.quote(str(source / "scripts/statechart"))})
    wrapper.chmod(0o755)


def install_statechart(home: Path, state: State, force: bool) -> None:
    """Fetch the pinned statechart skill and TLC jar, and link the skill into ~/.agents/skills."""
    pin = statechart_pin()
    root = home / STATECHART_ROOT
    state["statechart_root"] = str(root)
    write_json(home / MARKER, state)
    clone, jar, skill = root / "cursor-plugins", root / "tla2tools.jar", root / "skill"
    fetch_statechart_source(home, clone, pin)
    source = clone / pin["path"]
    if not (source / "SKILL.md").is_file() or not (source / "scripts/statechart").is_file():
        raise ValueError(f"statechart skill is missing from {source}")
    fetch_tla2tools(home, jar, pin)
    build_statechart_skill(skill, source, jar)
    managed_resource(home, state, home / STATECHART_LINK, skill, force, link=True)


def restore_resource(home: Path, key: str, record: dict) -> None:
    destination = home / key
    if destination.is_symlink():
        current = destination.readlink().as_posix()
    elif destination.is_file():
        current = hashlib.sha256(destination.read_bytes()).hexdigest()
    elif destination.exists():
        return
    else:
        current = None
    # A missing destination still gets its backup back: an earlier run may have failed between the two.
    if current is not None:
        if current != record.get("installed"):
            return
        destination.unlink()
    backup = record.get("backup")
    if backup and Path(backup).exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(backup, destination)


def uninstall_pi_skills(home: Path, state: State) -> None:
    """Take pi-skills back out and leave every other ported resource in place."""
    key = str(PI_SKILLS_LINK)
    record = state.get("ported_resources", {}).pop(key, None)
    if record:
        restore_resource(home, key, record)
    clone = state.pop("pi_skills_clone", None)
    if clone and Path(clone) == home / PI_SKILLS_CLONE and Path(clone).exists():
        shutil.rmtree(clone)
    write_json(home / MARKER, state)


def remove_statechart_files(state: State, home: Path) -> None:
    root = state.pop("statechart_root", None)
    if root and Path(root) == home / STATECHART_ROOT and Path(root).exists():
        shutil.rmtree(root)


def uninstall_statechart(home: Path, state: State) -> None:
    """Take the statechart skill back out and leave every other ported resource in place."""
    key = str(STATECHART_LINK)
    record = state.get("ported_resources", {}).pop(key, None)
    if record:
        restore_resource(home, key, record)
    remove_statechart_files(state, home)
    write_json(home / MARKER, state)


def uninstall_ported_resources(home: Path, state: State) -> None:
    for key, record in reversed(list(state.get("ported_resources", {}).items())):
        restore_resource(home, key, record)
    remove_statechart_files(state, home)
    prefix = state.get("ttt_prefix")
    if prefix and Path(prefix) == home / TTT_PREFIX and Path(prefix).exists():
        shutil.rmtree(prefix)
    clone = state.get("pi_skills_clone")
    if clone and Path(clone) == home / PI_SKILLS_CLONE and Path(clone).exists():
        shutil.rmtree(clone)
