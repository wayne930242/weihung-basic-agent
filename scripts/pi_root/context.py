"""What every install and uninstall step works on."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .jsonfile import write_json
from .paths import MARKER

State = dict[str, Any]


@dataclass(frozen=True)
class ModelsOverride:
    path: Path
    models: dict[str, Any]


@dataclass
class Context:
    home: Path
    state: State
    skip_external: bool = False
    force: bool = False
    first_install: bool = False
    # The install profile (unattended.PROFILES); a run without --profile keeps the one the marker recorded.
    profile: str = "default"
    models_override: ModelsOverride | None = None
    # Optional plugin checkouts an earlier install recorded and this machine no longer has.
    gone_plugins: list[str] = field(default_factory=list)

    @property
    def agent_dir(self) -> Path:
        return self.home / ".pi/agent"

    @property
    def settings_path(self) -> Path:
        return self.agent_dir / "settings.json"

    @property
    def herdr_config_path(self) -> Path:
        # pi-straw-boss's subagent host reads its models, status, and panes here, the file pi-herdr-agents read before it.
        return self.agent_dir / "herdr-agents/config.json"

    def save(self) -> None:
        """Record progress, so a run that fails later still restores what this one changed."""
        write_json(self.home / MARKER, self.state)
