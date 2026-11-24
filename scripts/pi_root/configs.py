"""The small managed settings: UI, terminal, panes, herdr-agents models, built-in MCP, mcp-adapter, open-tui, claude-bridge, computer use, compaction."""

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path

from .context import Context, ModelsOverride, State
from .jsonfile import read_json, write_json
from .managed import record_keys, remember_keys, restore_keys, restore_nested, restore_value
from . import unattended
from .paths import CLAUDE_BRIDGE_CONFIG, COMPUTER_USE_CONFIG, HERDR_MODELS, HERDR_MODELS_UNATTENDED, LENS_CONFIG, OPEN_TUI_CONFIG, RETIRED_ROLES_DIR, overlay_root

# pi's native compaction fires at contextWindow - reserveTokens: 500K for the 1M Opus and Sonnet, a
# ceiling for a long running turn; idle-compaction.ts compacts at 300K between turns.
OPUS_1M = "claude-bridge/claude-opus-5-5"
SONNET_1M = "claude-bridge/claude-sonnet-5-5"
COMPACTION_OVERRIDES = {OPUS_1M: {"reserveTokens": 500_000}, SONNET_1M: {"reserveTokens": 500_000}}
UI_SETTINGS = {"theme": "catppuccin-mocha", "editorPaddingX": 1, "collapseChangelog": True, "enableInstallTelemetry": False}
# install.sh puts codebase-memory-mcp in ~/.local/bin; registering it here replaces any copy imported from another
# agent's config, so its tools stay behind the `mcp` gateway instead of joining every prompt.
CODEBASE_MEMORY = "codebase-memory-mcp"
CODEBASE_MEMORY_BINARY = Path(".local/bin/codebase-memory-mcp")
MCP_SETTINGS = {"namespaceProxyTools": False}
# research-hub is no longer registered globally: the projects that use it register it in their own .mcp.json.
# An earlier install's entry is retired on the next install.
RESEARCH_HUB = "research-hub"
# pi-mcp-adapter owns /mcp; pi's built-in MCP support would otherwise warn on every start that it stepped aside.
BUILTIN_MCP_OFF = "-builtin:mcp"
# pi-herdr-agents falls back to its config.json.example only while config.json is missing; once this install creates the
# file, `status` is required, so a fresh machine gets the example's value (the other example sections have defaults).
HERDR_STATUS = {"enabled": True}
# pi-open-tui footer segments kept off to keep the footer to what gets read; `/open-tui` still owns every other setting.
OPEN_TUI_HIDDEN_SEGMENTS = ("runtime", "cost")
# The key an earlier install set in pi-computer-use's config (retired for agent-desktop); retire_computer_use gives it back.
COMPUTER_USE_SETTINGS = {"headless": True}


def write_or_remove(path: Path, value: dict) -> None:
    """Write what is left, or remove a file restoring emptied."""
    if value:
        write_json(path, value)
    elif path.exists():
        path.unlink()


def apply_ui(ctx: Context) -> None:
    state = ctx.state
    settings = read_json(ctx.settings_path)
    config = read_json(ctx.herdr_config_path)
    remember_keys(state, "ui_settings", settings, UI_SETTINGS)
    state.setdefault("previous_terminal", deepcopy(settings.get("terminal")))
    state.setdefault("previous_panes", deepcopy(config.get("panes")))
    settings.update(UI_SETTINGS)
    terminal = settings.setdefault("terminal", {})
    terminal["showTerminalProgress"] = True
    # pi treats TERM_PROGRAM=herdr as unable to show images, but herdr forwards kitty graphics to Ghostty.
    terminal["images"] = "kitty"
    disable_builtin_mcp(settings, state)
    if "status" not in config:
        config["status"] = deepcopy(HERDR_STATUS)
        state["added_herdr_status"] = True
    # Split placement opens each worker beside its caller's pane, in the caller's own tab.
    config["panes"] = {**config.get("panes", {}), "mode": "split", "direction": "right"}
    write_json(ctx.settings_path, settings)
    write_json(ctx.herdr_config_path, config)
    record_keys(state, "ui_settings", settings, UI_SETTINGS)
    state["installed_terminal"] = deepcopy(settings["terminal"])
    state["installed_panes"] = deepcopy(config["panes"])


def restore_ui(ctx: Context) -> None:
    state = ctx.state
    settings = read_json(ctx.settings_path)
    restore_keys(state, "ui_settings", settings, UI_SETTINGS)
    restore_nested(settings, "terminal", state.get("installed_terminal"), state.get("previous_terminal"), ("showTerminalProgress", "images"))
    restore_builtin_mcp(settings, state)
    write_json(ctx.settings_path, settings)
    config = read_json(ctx.herdr_config_path)
    restore_nested(config, "panes", state.get("installed_panes"), state.get("previous_panes"), ("mode", "direction"))
    if state.get("added_herdr_status") and config.get("status") == HERDR_STATUS:
        del config["status"]
    write_or_remove(ctx.herdr_config_path, config)


# Marker keys the removed model strategy profile wrote; none of them is read or restored any more.
RETIRED_PROFILE_KEYS = ("installed_agent_models", "installed_models", "installed_roles", "installed_settings",
                        "installed_status", "previous_models", "previous_settings", "previous_settings_present",
                        "previous_status", "strategy")


def retire_model_profile(ctx: Context) -> None:
    """Remove the tier roles an install with the model strategy profile wrote, and its marker keys."""
    state = ctx.state
    roles_dir = ctx.home / RETIRED_ROLES_DIR
    for name, digest in state.get("installed_roles", {}).items():
        path = roles_dir / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            path.unlink()
    if roles_dir.exists() and not any(roles_dir.iterdir()):
        roles_dir.rmdir()
    for key in RETIRED_PROFILE_KEYS:
        state.pop(key, None)


def models_source(ctx: Context) -> Path:
    return HERDR_MODELS_UNATTENDED if unattended.is_unattended(ctx.profile) else HERDR_MODELS


def load_models_override(state: State, path: Path | None, clear: bool) -> ModelsOverride | None:
    """Read and validate the host's chosen file before any install step writes to the home."""
    if clear:
        return None
    if path is None:
        if not (saved := state.get("herdr_models_file")):
            return None
        path = Path(saved)
    path = path.expanduser().absolute()
    if not path.is_file():
        raise ValueError(f"models file {path} does not exist or is not a regular file; "
                         "pass --models-file PATH to replace it or --no-models-file to clear it")
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"models file {path} is not valid JSON: {error}") from error
    except OSError as error:
        raise ValueError(f"cannot read models file {path}: {error}") from error

    def require_model_id(value: object, key: str) -> None:
        # A model ID can contain slashes (for example an OpenRouter model) or a colon suffix.
        if not isinstance(value, str) or not re.fullmatch(r"[\w.-]+(?:/[^/,\s*?\[\]]+)+", value):
            raise ValueError(f"models file {path}: {key} must be an exact provider/model ID (no comma lists)")

    if not isinstance(models, dict) or models.keys() != {"default", "agents", "tasks"}:
        raise ValueError(f"models file {path} must be a JSON object with exactly these keys: default, agents, tasks")
    require_model_id(models["default"], "default")
    for key in ("agents", "tasks"):
        if not isinstance(models[key], dict):
            raise ValueError(f"models file {path}: {key} must be an object")
    # The shared models tests require the default and unattended files to list the same roles and tasks.
    shared = read_json(HERDR_MODELS_UNATTENDED)
    for role, model in models["agents"].items():
        if role not in shared["agents"]:
            raise ValueError(f"models file {path}: agents.{role} is not a supported role")
        require_model_id(model, f"agents.{role}")
    for task, candidates in models["tasks"].items():
        if task not in shared["tasks"]:
            raise ValueError(f"models file {path}: tasks.{task} is not a supported task category")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"models file {path}: tasks.{task} must be a nonempty array")
        for index, model in enumerate(candidates):
            require_model_id(model, f"tasks.{task}[{index}]")
        if len(set(candidates)) != len(candidates):
            raise ValueError(f"models file {path}: tasks.{task} contains duplicate model IDs")
    return ModelsOverride(path, models)


def apply_herdr_models(ctx: Context) -> None:
    """Write the host override or profile's shared models; a hand edit since the last install stops the run."""
    retire_model_profile(ctx)
    state = ctx.state
    config = read_json(ctx.herdr_config_path)
    override = ctx.models_override
    source = override.path if override else models_source(ctx)
    desired = override.models if override else read_json(source)
    current = config.get("models")
    edited = current not in (None, desired, state.get("installed_herdr_models"))
    if edited and not ctx.force:
        raise ValueError(f"{ctx.herdr_config_path} `models` differs from {source}; move the change into the "
                         "source file, or rerun with --force to replace it")
    state.setdefault("previous_herdr_models", deepcopy(current))
    config["models"] = desired
    write_json(ctx.herdr_config_path, config)
    state["installed_herdr_models"] = deepcopy(desired)
    if override:
        state["herdr_models_file"] = str(override.path)
    else:
        state.pop("herdr_models_file", None)


def restore_herdr_models(ctx: Context) -> None:
    state = ctx.state
    config = read_json(ctx.herdr_config_path)
    restore_value(config, "models", state.get("installed_herdr_models"), state.get("previous_herdr_models"))
    write_or_remove(ctx.herdr_config_path, config)


def overlay_model_providers() -> dict:
    """The providers the overlay's pi/models.json declares, or none without an overlay or that file."""
    root = overlay_root()
    return read_json(root / "pi/models.json").get("providers", {}) if root else {}


def apply_overlay_models(ctx: Context) -> None:
    """Merge the overlay's model providers into ~/.pi/agent/models.json; a provider edited by hand stops the run."""
    state = ctx.state
    path = ctx.agent_dir / "models.json"
    config = read_json(path)
    providers = config.get("providers", {})
    installed = state.get("installed_model_providers", {})
    previous = state.setdefault("previous_model_providers", {})
    desired = overlay_model_providers()
    for name, value in desired.items():
        current = providers.get(name)
        if current not in (None, value, installed.get(name)) and not ctx.force:
            raise ValueError(f"{path} provider `{name}` differs from the overlay's pi/models.json; move the change into "
                             "the overlay, or rerun with --force to replace it")
        if name not in installed:
            previous.setdefault(name, deepcopy(current))
        providers[name] = deepcopy(value)
    # A provider the overlay dropped goes back to what it replaced, while it still holds what install wrote.
    for name in set(installed) - set(desired):
        restore_value(providers, name, installed[name], previous.pop(name, None))
    if providers:
        config["providers"] = providers
    else:
        config.pop("providers", None)
    write_or_remove(path, config)
    state["installed_model_providers"] = deepcopy(desired)


def restore_overlay_models(ctx: Context) -> None:
    state = ctx.state
    path = ctx.agent_dir / "models.json"
    config = read_json(path)
    providers = config.get("providers", {})
    previous = state.get("previous_model_providers", {})
    for name, value in state.get("installed_model_providers", {}).items():
        restore_value(providers, name, value, previous.get(name))
    if providers:
        config["providers"] = providers
    else:
        config.pop("providers", None)
    write_or_remove(path, config)


def overlay_trusted_dirs(home: Path) -> list[str]:
    """The directories the overlay's pi/trust.json lists, `~` expanded and canonical like pi's own trust keys."""
    root = overlay_root()
    dirs = read_json(root / "pi/trust.json").get("trusted", []) if root else []
    return [os.path.realpath(home / entry[2:] if entry.startswith("~/") else entry) for entry in dirs]


def apply_overlay_trust(ctx: Context) -> None:
    """Mark the overlay's directories trusted in ~/.pi/agent/trust.json; pi trusts every directory below a trusted one."""
    state = ctx.state
    path = ctx.agent_dir / "trust.json"
    trust = read_json(path)
    installed = state.get("installed_trusted_dirs", [])
    previous = state.setdefault("previous_trusted_dirs", {})
    desired = overlay_trusted_dirs(ctx.home)
    for key in desired:
        if key not in installed:
            previous.setdefault(key, trust.get(key))
        trust[key] = True
    # A directory the overlay dropped goes back to its earlier decision, while it still holds what install wrote.
    for key in set(installed) - set(desired):
        restore_value(trust, key, True, previous.pop(key, None))
    write_or_remove(path, dict(sorted(trust.items())))
    state["installed_trusted_dirs"] = desired


def restore_overlay_trust(ctx: Context) -> None:
    state = ctx.state
    path = ctx.agent_dir / "trust.json"
    trust = read_json(path)
    previous = state.get("previous_trusted_dirs", {})
    for key in state.get("installed_trusted_dirs", []):
        restore_value(trust, key, True, previous.get(key))
    write_or_remove(path, trust)


def overlay_claude_settings() -> dict[str, object]:
    """The overlay's claude/settings.json as managed entries: a top-level key, or `key.sub` for each entry of an object
    such as `env`, so the user's own entries beside them stay theirs."""
    root = overlay_root()
    entries: dict[str, object] = {}
    for key, value in (read_json(root / "claude/settings.json") if root else {}).items():
        if isinstance(value, dict):
            entries.update({f"{key}.{sub}": item for sub, item in value.items()})
        else:
            entries[key] = value
    return entries


def _claude_slot(settings: dict, entry: str, create: bool) -> tuple[dict | None, str]:
    """The object holding a managed entry and its key there; None when its parent object is missing."""
    if "." not in entry:
        return settings, entry
    parent, key = entry.split(".", 1)
    if create:
        settings.setdefault(parent, {})
    container = settings.get(parent)
    return (container if isinstance(container, dict) else None), key


def _drop_empty_parent(settings: dict, entry: str) -> None:
    parent = entry.split(".", 1)[0]
    if "." in entry and settings.get(parent) == {}:
        settings.pop(parent)


def apply_overlay_claude_settings(ctx: Context) -> None:
    """Merge the overlay's Claude Code settings into ~/.claude/settings.json; an entry edited by hand stops the run."""
    state = ctx.state
    path = ctx.home / ".claude/settings.json"
    desired = overlay_claude_settings()
    installed = state.get("installed_claude_settings", {})
    if not desired and not installed:
        return
    settings = read_json(path)
    previous = state.setdefault("previous_claude_settings", {})
    for entry, value in desired.items():
        container, key = _claude_slot(settings, entry, create=True)
        if container is None:
            raise ValueError(f"{path} `{entry.split('.', 1)[0]}` is not an object")
        current = container.get(key)
        if current not in (None, value, installed.get(entry)) and not ctx.force:
            raise ValueError(f"{path} `{entry}` differs from the overlay's claude/settings.json; move the change into "
                             "the overlay, or rerun with --force to replace it")
        if entry not in installed:
            previous.setdefault(entry, deepcopy(current))
        container[key] = deepcopy(value)
    # An entry the overlay dropped goes back to what it replaced, while it still holds what install wrote.
    for entry in set(installed) - set(desired):
        container, key = _claude_slot(settings, entry, create=False)
        if container is not None:
            restore_value(container, key, installed[entry], previous.pop(entry, None))
            _drop_empty_parent(settings, entry)
    write_or_remove(path, settings)
    state["installed_claude_settings"] = deepcopy(desired)


def restore_overlay_claude_settings(ctx: Context) -> None:
    state = ctx.state
    installed = state.get("installed_claude_settings", {})
    if not installed:
        return
    path = ctx.home / ".claude/settings.json"
    settings = read_json(path)
    previous = state.get("previous_claude_settings", {})
    for entry, value in installed.items():
        container, key = _claude_slot(settings, entry, create=False)
        if container is not None:
            restore_value(container, key, value, previous.get(entry))
            _drop_empty_parent(settings, entry)
    write_or_remove(path, settings)


def disable_builtin_mcp(settings: dict, state: State) -> None:
    extensions = settings.get("extensions")
    state.setdefault("previous_extensions_present", extensions is not None)
    state.setdefault("added_builtin_mcp_off", BUILTIN_MCP_OFF not in (extensions or []))
    if BUILTIN_MCP_OFF not in (extensions or []):
        settings["extensions"] = [*(extensions or []), BUILTIN_MCP_OFF]


def restore_builtin_mcp(settings: dict, state: State) -> None:
    extensions = settings.get("extensions")
    if not state.get("added_builtin_mcp_off") or not isinstance(extensions, list):
        return
    settings["extensions"] = [item for item in extensions if item != BUILTIN_MCP_OFF]
    if not settings["extensions"] and not state.get("previous_extensions_present", True):
        settings.pop("extensions")


def mcp_config_path(agent_dir: Path) -> Path:
    """The adapter's own settings file; mcp.json stays pi's, which pi-mcp-adapter 5.0.0 also reads."""
    return agent_dir / "mcp-adapter.json"


def apply_mcp(ctx: Context) -> None:
    path = mcp_config_path(ctx.agent_dir)
    mcp = read_json(path)
    update_mcp(mcp, ctx.state, ctx.home)
    write_json(path, mcp)


def update_mcp(mcp: dict, state: State, home: Path) -> None:
    state.setdefault("previous_discovery", mcp.get("settings", {}).get("hostConfigDiscovery"))
    settings = mcp.setdefault("settings", {})
    state.setdefault("previous_mcp_settings", {key: deepcopy(settings[key]) for key in MCP_SETTINGS if key in settings})
    settings["hostConfigDiscovery"] = "on"
    settings.update(MCP_SETTINGS)
    servers = mcp.setdefault("mcpServers", {})
    state.setdefault("previous_mcp_server", deepcopy(servers.get(CODEBASE_MEMORY)))
    servers[CODEBASE_MEMORY] = {"command": str(home / CODEBASE_MEMORY_BINARY)}
    state["installed_mcp_settings"] = dict(MCP_SETTINGS)
    state["installed_mcp_server"] = deepcopy(servers[CODEBASE_MEMORY])
    retire_research_hub(servers, state)


def retire_research_hub(servers: dict, state: State) -> None:
    """Give back the research-hub entry an earlier install replaced, unless the user changed it since."""
    if "installed_research_hub_server" in state:
        restore_value(servers, RESEARCH_HUB, state["installed_research_hub_server"], state.get("previous_research_hub_server"))
    for key in ("previous_research_hub_server", "installed_research_hub_server"):
        state.pop(key, None)


def restore_mcp(ctx: Context) -> None:
    state = ctx.state
    path = mcp_config_path(ctx.agent_dir)
    mcp = read_json(path)
    if mcp.get("settings", {}).get("hostConfigDiscovery") == "on":
        previous = state.get("previous_discovery")
        if previous is None:
            mcp["settings"].pop("hostConfigDiscovery", None)
        else:
            mcp["settings"]["hostConfigDiscovery"] = previous
    restore_nested(mcp, "settings", state.get("installed_mcp_settings"), state.get("previous_mcp_settings"), tuple(MCP_SETTINGS))
    if "mcpServers" in mcp:
        restore_value(mcp["mcpServers"], CODEBASE_MEMORY, state.get("installed_mcp_server"), state.get("previous_mcp_server"))
        # A marker from an install before the retirement still records the research-hub entry it wrote.
        if "installed_research_hub_server" in state:
            restore_value(mcp["mcpServers"], RESEARCH_HUB, state["installed_research_hub_server"], state.get("previous_research_hub_server"))
        if not mcp["mcpServers"]:
            mcp.pop("mcpServers")
    if mcp.get("settings") == {}:
        mcp.pop("settings")
    write_or_remove(path, mcp)


def retire_lens(ctx: Context) -> None:
    """pi-lens is retired: give back ~/.pi-lens/config.json as it was before an earlier install managed it."""
    state = ctx.state
    if "installed_lens_tools" in state or "installed_lens_dispatch" in state:
        restore_lens(ctx)
    for key in ("previous_lens_tools", "installed_lens_tools", "previous_lens_dispatch", "installed_lens_dispatch"):
        state.pop(key, None)


def restore_lens(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / LENS_CONFIG
    config = read_json(path)
    if "installed_lens_dispatch" in state:
        restore_nested(config, "dispatch", state["installed_lens_dispatch"], state.get("previous_lens_dispatch"), ("disabledRunners",))
    tools = config.get("tools")
    if isinstance(tools, dict) and "installed_lens_tools" in state:
        previous = state.get("previous_lens_tools", {})
        for name, installed in state["installed_lens_tools"].items():
            restore_nested(tools, name, installed, previous.get(name), ("enabled",))
        if not tools:
            config.pop("tools")
    write_or_remove(path, config)


def apply_open_tui(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / OPEN_TUI_CONFIG
    config = read_json(path)
    segments = config.setdefault("footerSegments", {})
    state.setdefault("previous_open_tui_present", path.exists())
    state.setdefault("previous_open_tui_segments", {name: segments[name] for name in OPEN_TUI_HIDDEN_SEGMENTS if name in segments})
    segments.update(dict.fromkeys(OPEN_TUI_HIDDEN_SEGMENTS, False))
    write_json(path, config)
    state["installed_open_tui_segments"] = dict.fromkeys(OPEN_TUI_HIDDEN_SEGMENTS, False)


def restore_open_tui(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / OPEN_TUI_CONFIG
    config = read_json(path)
    if "installed_open_tui_segments" not in state:
        return
    restore_nested(config, "footerSegments", state["installed_open_tui_segments"],
                   state.get("previous_open_tui_segments"), OPEN_TUI_HIDDEN_SEGMENTS)
    if config or state.get("previous_open_tui_present", True):
        write_json(path, config)
    elif path.exists():
        path.unlink()


def retire_computer_use(ctx: Context) -> None:
    """pi-computer-use is retired: give back its config file as it was before an earlier install set `headless`."""
    state = ctx.state
    if "installed_computer_use" in state:
        restore_computer_use(ctx)
    for key in ("previous_computer_use", "previous_computer_use_present", "installed_computer_use", "previous_computer_use_file_present"):
        state.pop(key, None)


def restore_computer_use(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / COMPUTER_USE_CONFIG
    if "installed_computer_use" not in state or not path.exists():
        return
    config = read_json(path)
    restore_keys(state, "computer_use", config, COMPUTER_USE_SETTINGS)
    if config or state.get("previous_computer_use_file_present", True):
        write_json(path, config)
    else:
        path.unlink()


# pi-claude-bridge sends Claude Code's system prompt preset ahead of pi's own unless provider.systemPromptPreset is false;
# pi's prompt alone is the whole system prompt on every machine and profile (the boss's decision, 2026-11-16).
CLAUDE_BRIDGE_PROVIDER = {"systemPromptPreset": False}


def apply_claude_bridge(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / CLAUDE_BRIDGE_CONFIG
    config = read_json(path)
    state.setdefault("previous_claude_bridge_present", path.exists())
    provider = config.setdefault("provider", {})
    state.setdefault("previous_claude_bridge_provider", {key: provider[key] for key in CLAUDE_BRIDGE_PROVIDER if key in provider})
    provider.update(CLAUDE_BRIDGE_PROVIDER)
    write_json(path, config)
    state["installed_claude_bridge_provider"] = deepcopy(CLAUDE_BRIDGE_PROVIDER)


def restore_claude_bridge(ctx: Context) -> None:
    state = ctx.state
    path = ctx.home / CLAUDE_BRIDGE_CONFIG
    if "installed_claude_bridge_provider" not in state:
        return
    config = read_json(path)
    restore_nested(config, "provider", state["installed_claude_bridge_provider"],
                   state.get("previous_claude_bridge_provider"), tuple(CLAUDE_BRIDGE_PROVIDER))
    if config or state.get("previous_claude_bridge_present", True):
        write_json(path, config)
    elif path.exists():
        path.unlink()


def apply_compaction(ctx: Context) -> None:
    state = ctx.state
    settings = read_json(ctx.settings_path)
    state.setdefault("previous_compaction_present", "compaction" in settings)
    compaction = settings.setdefault("compaction", {})
    state.setdefault("previous_compaction_overrides", deepcopy(compaction.get("modelOverrides")))
    compaction["modelOverrides"] = {**(compaction.get("modelOverrides") or {}), **deepcopy(COMPACTION_OVERRIDES)}
    write_json(ctx.settings_path, settings)
    state["installed_compaction_overrides"] = deepcopy(compaction["modelOverrides"])


def restore_compaction(ctx: Context) -> None:
    state = ctx.state
    settings = read_json(ctx.settings_path)
    compaction = settings.get("compaction")
    if not isinstance(compaction, dict):
        return
    restore_nested(compaction, "modelOverrides", state.get("installed_compaction_overrides"),
                   state.get("previous_compaction_overrides"), tuple(COMPACTION_OVERRIDES))
    if not compaction and not state.get("previous_compaction_present", True):
        settings.pop("compaction")
    write_json(ctx.settings_path, settings)
