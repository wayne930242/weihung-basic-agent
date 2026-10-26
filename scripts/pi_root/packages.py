"""Pi packages: identity, the packages this repository owns, and the install step that also brings the tools they need."""

import os
import subprocess
import sys
from pathlib import Path

from . import external, resources
from .context import Context, State
from .jsonfile import read_json, write_json
from .paths import (
    ANCHORLOOP_ROOT_VARIABLE,
    HERDR_AGENTS_ROOT_VARIABLE,
    LOCAL_PACKAGE,
    optional_plugins,
    overlay_root,
)
from .pins import (
    ANCHORLOOP_PACKAGE,
    HERDR_AGENTS_SOURCE,
    HERDR_PLUGINS,
    PACKAGES,
    PINNED_GIT,
    PLAYWRITER,
    RETIRED_SOURCES,
)

Package = str | dict


def package_source(value: Package) -> str:
    return value["source"] if isinstance(value, dict) else value


def package_id(value: Package, agent_dir: Path) -> str:
    source = package_source(value)
    if source.startswith("npm:"):
        # Pi identifies npm packages by name, so a pinned spec replaces its unpinned predecessor.
        spec = source.removeprefix("npm:")
        return "npm:" + spec[:spec.find("@", 1)] if spec.find("@", 1) > 0 else source
    if source.startswith("git:"):
        return source
    return str((agent_dir / source).resolve())


def unique_packages(values: list[Package], agent_dir: Path) -> list[Package]:
    seen = set()
    result = []
    for value in values:
        identity = package_id(value, agent_dir)
        if identity not in seen:
            seen.add(identity)
            result.append(value)
    return result


def obsolete_pin(value: Package) -> bool:
    source = package_source(value)
    return (any(source.startswith(prefixes) and source != current for current, prefixes in PINNED_GIT.items())
            or source.startswith(RETIRED_SOURCES))


def anchorloop_source() -> str:
    """The pinned anchorloop release, or the checkout PI_ANCHORLOOP_ROOT names for testing."""
    value = os.environ.get(ANCHORLOOP_ROOT_VARIABLE)
    if not value:
        return ANCHORLOOP_PACKAGE
    root = Path(value).expanduser().resolve()
    if not (root / "package.json").is_file():
        raise ValueError(f"{ANCHORLOOP_ROOT_VARIABLE}={value} has no package.json; point it at a checkout or unset it to use {ANCHORLOOP_PACKAGE}")
    return str(root)



def plugin_source(name: str, variable: str, default: Path) -> str | None:
    root = Path(os.environ.get(variable, default)).resolve()
    if (root / "package.json").is_file():
        return str(root)
    print(f"{name} not found at {root}; skipped. Set {variable} to the plugin checkout and rerun to add it.", file=sys.stderr)
    return None


def herdr_agents_root() -> str | None:
    """The checkout named by PI_HERDR_AGENTS_ROOT, or None when the variable is unset; a wrong value fails the install."""
    value = os.environ.get(HERDR_AGENTS_ROOT_VARIABLE)
    if not value:
        return None
    root = Path(value).expanduser().resolve()
    manifest = root / "package.json"
    if not manifest.is_file():
        raise ValueError(f"{HERDR_AGENTS_ROOT_VARIABLE}={value} has no package.json at {manifest}; "
                         f"point it at a pi-herdr-agents checkout or unset it to use {HERDR_AGENTS_SOURCE}")
    name = read_json(manifest).get("name")
    if name != "pi-herdr-agents":
        raise ValueError(f"{HERDR_AGENTS_ROOT_VARIABLE}={value} is the package {name!r}, not pi-herdr-agents")
    return str(root)


def owned_packages(state: State) -> list[Package]:
    """PACKAGES, with the pinned pi-herdr-agents release swapped for the override checkout the install recorded."""
    return [state["herdr_agents"] if package == HERDR_AGENTS_SOURCE and state.get("herdr_agents") else package
            for package in PACKAGES]


def plugin_keys(state: State) -> list[str]:
    """The overlay's optional plugins, including those the install recorded from an overlay that is gone now."""
    return list(dict.fromkeys([*state.get("overlay_plugins", []), *optional_plugins()]))


def local_packages(state: State) -> list[Package]:
    return [state.get("anchorloop", ANCHORLOOP_PACKAGE), LOCAL_PACKAGE, *(state[key] for key in plugin_keys(state) if state.get(key))]


def plan(ctx: Context) -> None:
    """Record which package sources this run uses and what settings held before the first install."""
    state = ctx.state
    herdr_root = ctx.herdr_root
    # A source that changed form (checkout to npm or back, or the git install aaaav had before 1.0, or pi-aaaav before its rename) leaves settings like a displaced pi-herdr-agents root;
    # so does a straw-boss checkout from before Straw Boss moved to the pi-straw-boss npm package.
    sources = {"anchorloop": anchorloop_source()}
    state["latest_displaced"] = [old for old in dict.fromkeys([*state.get("latest_displaced", []), state.pop("straw_boss", None), state.pop("aaaav", None),
                                 *(state.get(key) for key in sources)]) if old and old not in sources.values()]
    state.update(sources)
    # pi identifies an npm package by name but a local one by path, so whichever form the other mode used must leave settings.
    # Old checkouts stay recorded until a run completes, so a run that fails midway still removes them on the next one.
    state["herdr_agents_displaced"] = [root for root in dict.fromkeys([*state.get("herdr_agents_displaced", []), state.get("herdr_agents")])
                                       if root and root != herdr_root]
    if herdr_root:
        state["herdr_agents"] = herdr_root
        print(f"{HERDR_AGENTS_ROOT_VARIABLE}: using {herdr_root} instead of {HERDR_AGENTS_SOURCE}. "
              "Roles still come from pi-herdr-roles and the agents/ overrides.", file=sys.stderr)
    else:
        state.pop("herdr_agents", None)
    declared = optional_plugins()
    for key in plugin_keys(state):
        if key in declared and (source := plugin_source(*declared[key])):
            state[key] = source
        elif key in state:
            ctx.gone_plugins.append(state.pop(key))
    state["overlay_plugins"] = list(declared)
    settings = read_json(ctx.settings_path)
    state["previous_packages"] = state.get("previous_packages", list(settings.get("packages", [])))
    state.setdefault("retired_packages", [package for package in settings.get("packages", []) if obsolete_pin(package)])
    state.setdefault("integration_installed", not ctx.first_install)


# herdr web ui was the remote control until it was retired; an install that added the plugin removes it once.
HERDR_WEB_UI_ID = "devswha.herdr-web-ui"


def retire_herdr_web_ui(ctx: Context) -> None:
    if "herdr_web_ui_preinstalled" not in ctx.state:
        return
    # `herdr plugin uninstall` fails on a plugin that is not there, which an install with a failed build left behind.
    if not ctx.state["herdr_web_ui_preinstalled"] and HERDR_WEB_UI_ID in external.capture(["herdr", "plugin", "list"], ctx.home):
        external.run(["herdr", "plugin", "uninstall", HERDR_WEB_UI_ID], ctx.home)
    ctx.state.pop("herdr_web_ui_preinstalled")
    ctx.save()


def plugin_line(home: Path, plugin_id: str) -> str | None:
    """A plugin's line in `herdr plugin list`, or None when it is not installed."""
    listed = external.capture(["herdr", "plugin", "list"], home)
    # One id can begin another (straw-boss, straw-boss-reaper), and each plugin's config line names its id too.
    return next((line for line in listed.splitlines() if f"{plugin_id} (" in line), None)


def install_herdr_plugins(ctx: Context) -> None:
    """Install each Herdr plugin at its pinned tag; a plugin at another source or tag is replaced."""
    for plugin_id, repo, ref, preinstalled in HERDR_PLUGINS:
        line = plugin_line(ctx.home, plugin_id)
        if preinstalled not in ctx.state:
            ctx.state[preinstalled] = line is not None
            ctx.save()
        if line and f"github:{repo}@{ref}" in line:
            continue
        if line:
            external.run(["herdr", "plugin", "uninstall", plugin_id], ctx.home)
        external.run(["herdr", "plugin", "install", repo, "--ref", ref, "--yes"], ctx.home)


def apply(ctx: Context) -> None:
    """Install pi, its tools, and every owned package, then write the package list in the order pi expects."""
    home, state, agent_dir, settings_path = ctx.home, ctx.state, ctx.agent_dir, ctx.settings_path
    old_roots = state["herdr_agents_displaced"] + state["latest_displaced"]
    # The other form of pi-herdr-agents leaves settings even when the user had declared it first.
    retired_ids = {package_id(value, agent_dir) for value in old_roots + ([HERDR_AGENTS_SOURCE] if ctx.herdr_root else [])}
    # An overlay checkout is not a pi package; a machine whose settings still list it from before the overlay split sheds it.
    if overlay := overlay_root():
        retired_ids.add(package_id(str(overlay), agent_dir))
    pinned = owned_packages(state)
    if not ctx.skip_external:
        external.run(["npm", "install", "-g", "@earendil-works/pi-coding-agent@latest"], home)
        if "playwriter_preinstalled" not in state:
            listed = subprocess.run(["npm", "ls", "-g", "--depth=0", "playwriter"], capture_output=True, check=False)
            state["playwriter_preinstalled"] = listed.returncode == 0
            ctx.save()
        external.run(["npm", "install", "-g", PLAYWRITER], home)
        external.run(["herdr", "integration", "install", "pi"], home)
        state["integration_installed"] = True
        ctx.save()
        retire_herdr_web_ui(ctx)
        install_herdr_plugins(ctx)
        for package in pinned:
            external.run(["pi", "install", package_source(package)], home)
        for package in state["retired_packages"]:
            settings = read_json(settings_path)
            if package not in settings.get("packages", []):
                continue
            if package.startswith("git:"):
                settings["packages"] = [value for value in settings["packages"] if value != package]
                write_json(settings_path, settings)
            else:
                external.run(["pi", "remove", package], home)
        for package in read_json(settings_path).get("packages", []):
            if package_id(package, agent_dir) in retired_ids:
                external.run(["pi", "remove", package_source(package)], home)
        external.run(["pi", "install", state["anchorloop"]], home)
        resources.install_ported_resources(home, state, ctx.force)
        ctx.save()
        external.run(["pi", "install", LOCAL_PACKAGE], home)
        for key in plugin_keys(state):
            if state.get(key):
                external.run_optional_plugin("install", home, state[key])
    else:
        settings = read_json(settings_path)
        settings["packages"] = [package for package in unique_packages(settings.get("packages", []) + pinned + local_packages(state), agent_dir)
                                if not obsolete_pin(package)]
        write_json(settings_path, settings)
    settings = read_json(settings_path)
    current = settings.get("packages", [])
    owned = pinned + local_packages(state)
    owned_ids = {package_id(value, agent_dir) for value in owned}
    unmanaged = [value for value in current
                 if package_id(value, agent_dir) not in owned_ids | retired_ids and not obsolete_pin(value)]
    # Registry and git specs are written as declared; `pi install` records a local path relative to the agent directory.
    declared = [source if package_source(source).startswith(("npm:", "git:")) else
                next((value for value in current if package_id(value, agent_dir) == package_id(source, agent_dir)), source)
                for source in owned]
    gone_ids = {package_id(value, agent_dir) for value in ctx.gone_plugins}
    settings["packages"] = [value for value in unique_packages(unmanaged + declared, agent_dir)
                            if package_id(value, agent_dir) not in gone_ids]
    write_json(settings_path, settings)
    state.pop("herdr_agents_displaced")
    state.pop("latest_displaced")


def restore(ctx: Context) -> None:
    """Remove what install added and put back the packages and tools the user had before it."""
    home, state, agent_dir, settings_path = ctx.home, ctx.state, ctx.agent_dir, ctx.settings_path
    resources.uninstall_ported_resources(home, state)
    previous_packages = state.get("previous_packages", [])
    previous_ids = {package_id(value, agent_dir) for value in previous_packages}
    managed_packages = owned_packages(state) + local_packages(state)
    optional = [state[key] for key in plugin_keys(state) if state.get(key)]
    owned = {package_id(value, agent_dir) for value in managed_packages} - previous_ids
    if not ctx.skip_external:
        installed_ids = {package_id(value, agent_dir) for value in read_json(settings_path).get("packages", [])}
        for package in managed_packages:
            identity = package_id(package, agent_dir)
            if identity in owned and identity in installed_ids:
                if package in optional:
                    external.run_optional_plugin("remove", home, package_source(package))
                else:
                    external.run(["pi", "remove", package_source(package)], home)
        if state.get("integration_installed", True):
            external.run(["herdr", "integration", "uninstall", "pi"], home)
        retire_herdr_web_ui(ctx)
        # A plugin the user had before install stays; one install added goes.
        for plugin_id, _, _, preinstalled in HERDR_PLUGINS:
            if not state.get(preinstalled, True) and plugin_line(home, plugin_id):
                external.run(["herdr", "plugin", "uninstall", plugin_id], home)
        if not state.get("playwriter_preinstalled", True):
            external.run(["npm", "uninstall", "-g", "playwriter"], home)
    settings = read_json(settings_path)
    # A package the user declared before install keeps the spec they wrote, not the pinned one.
    prior = {package_id(value, agent_dir): value for value in previous_packages}
    settings["packages"] = [prior.get(package_id(package, agent_dir), package) for package in settings.get("packages", [])
                            if package_id(package, agent_dir) not in owned]
    # The override replaced a release the user had declared before install; put that spec back like a retired package.
    displaced = [package for package in previous_packages if state.get("herdr_agents")
                 and package_id(package, agent_dir) == package_id(HERDR_AGENTS_SOURCE, agent_dir)]
    for package in [*state.get("retired_packages", []), *displaced]:
        if package not in settings["packages"]:
            if not ctx.skip_external:
                external.run(["pi", "install", package], home)
            settings["packages"].append(package)
    settings["packages"] = unique_packages(
        [package for package in previous_packages if package in settings["packages"]] + settings["packages"], agent_dir
    )
    if not settings["packages"]:
        settings.pop("packages")
    write_json(settings_path, settings)
