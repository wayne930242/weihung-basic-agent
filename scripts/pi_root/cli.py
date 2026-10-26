"""The pi-target.py command line."""

import argparse
import os
from pathlib import Path

from . import packages, steps
from .paths import OVERLAY_VARIABLE, saved_overlay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "install", "uninstall", "saved-overlay"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-overlay", action="store_true", help="install without the overlay the last install recorded")
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if args.action == "saved-overlay":
        # install.sh and uninstall.sh ask for the overlay the last install recorded when they are not given one.
        print(saved_overlay(home) or "")
        return
    # A run without --overlay keeps the overlay the last install recorded, so a bare public install or uninstall
    # (the pi-pins auto-update, for one) never drops the layer.
    if args.no_overlay:
        os.environ.pop(OVERLAY_VARIABLE, None)
    elif not os.environ.get(OVERLAY_VARIABLE) and (saved := saved_overlay(home)):
        os.environ[OVERLAY_VARIABLE] = saved
    # install.sh runs `migrate` first, so a wrong override stops there, before any link changes a file.
    herdr_root = packages.herdr_agents_root() if args.action in ("migrate", "install") else None
    if args.action == "install":
        steps.install(home, args.skip_external, args.force, herdr_root)
    elif args.action == "uninstall":
        steps.uninstall(home, args.skip_external)
