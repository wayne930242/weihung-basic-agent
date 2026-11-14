"""The unattended profile's `tower-mode` command: scripts/tower-mode.mjs linked into ~/.local/bin.

The box reads its pickup mode from hq through it before every ticket claim and every new train (MP-4705). Only the unattended
profile installs it; a run under another profile takes it back out.
"""

from . import resources, unattended
from .context import Context
from .paths import ROOT

LINK = ".local/bin/tower-mode"
SOURCE = ROOT / "scripts/tower-mode.mjs"


def apply(ctx: Context) -> None:
    if not unattended.is_unattended(ctx.profile):
        remove(ctx)
        return
    if not SOURCE.is_file():
        raise ValueError(f"tower-mode script is missing: {SOURCE}")
    resources.managed_resource(ctx.home, ctx.state, ctx.home / LINK, SOURCE, ctx.force, link=True)


def remove(ctx: Context) -> None:
    record = ctx.state.get("ported_resources", {}).pop(LINK, None)
    if record:
        resources.restore_resource(ctx.home, LINK, record)


restore = remove
