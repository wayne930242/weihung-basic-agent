"""Where the repository, the marker, and the managed files live; roots other checkouts may override."""

import os
from pathlib import Path

from .jsonfile import read_json

ROOT = Path(__file__).resolve().parents[2]
MARKER = Path(".pi/agent/.weihung-agent-root.json")
LOCAL_PACKAGE = str(ROOT)
# Testing an unreleased pi-herdr-agents fix: this variable names a checkout that replaces the pinned release.
HERDR_AGENTS_ROOT_VARIABLE = "PI_HERDR_AGENTS_ROOT"
# Testing an unpushed anchorloop change: this variable names a checkout that replaces the latest commit.
ANCHORLOOP_ROOT_VARIABLE = "PI_ANCHORLOOP_ROOT"
# The pi-herdr-agents `models` object (role, default, and task models) this repository writes into its config.
HERDR_MODELS = ROOT / "pi/herdr-agents-models.json"
# The model strategy profile was removed; its generated tier roles and marker keys are retired on install.
RETIRED_ROLES_DIR = Path(".pi/agent/herdr-agents/roles")
LENS_CONFIG = Path(".pi-lens/config.json")
OPEN_TUI_CONFIG = Path(".pi/agent/open-tui.json")
COMPUTER_USE_CONFIG = Path(".pi/agent/extensions/pi-computer-use.json")
TTT_PREFIX = Path(".local/share/weihung-agent-root/team-toon-tack")
# pi-skills ships bare skill directories without a pi manifest; its README installs it as a clone under the skills root.
PI_SKILLS_GIT = os.environ.get("PI_SKILLS_GIT", "https://github.com/badlogic/pi-skills.git")
PI_SKILLS_CLONE = Path(".local/share/weihung-agent-root/pi-skills")
# An overlay is a second checkout layered over this one: its skills/ directory is linked beside ours, its pi/AGENTS.append.md
# is appended to the generated AGENTS.md, and its overlay.json may declare optional plugins. install.sh --overlay sets the variable.
OVERLAY_VARIABLE = "WEIHUNG_OVERLAY"


def overlay_root() -> Path | None:
    value = os.environ.get(OVERLAY_VARIABLE)
    return Path(value).expanduser().resolve() if value else None


def saved_overlay(home: Path) -> str | None:
    """The overlay the last install recorded in the marker, or None when it ran without one."""
    return read_json(home / MARKER).get("overlay")


def optional_plugins() -> dict[str, tuple[str, str, Path]]:
    """Key, display name, root variable, and default checkout of each optional plugin the overlay declares.

    A plugin is a pi package in a checkout that may be absent: a machine without it skips it. overlay.json holds
    {"plugins": {key: {"name": ..., "variable": ..., "path": <relative to the overlay>}}}.
    """
    root = overlay_root()
    if root is None:
        return {}
    config = read_json(root / "overlay.json").get("plugins", {})
    return {key: (entry["name"], entry["variable"], (root / entry["path"]).resolve()) for key, entry in config.items()}
