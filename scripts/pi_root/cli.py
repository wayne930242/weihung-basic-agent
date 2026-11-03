"""The pi-target.py command line."""

import argparse
import os
from pathlib import Path

from . import packages, steps, unattended
from .paths import OVERLAY_VARIABLE, saved_overlay, saved_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "install", "uninstall", "saved-overlay", "saved-profile", "dropped-skills"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-overlay", action="store_true", help="install without the overlay the last install recorded")
    parser.add_argument("--profile", choices=unattended.PROFILES, help="install profile; a run without it keeps the recorded one")
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if args.action == "saved-overlay":
        # install.sh and uninstall.sh ask for the overlay the last install recorded when they are not given one.
        print(saved_overlay(home) or "")
        return
    if args.action in ("saved-profile", "dropped-skills"):
        # install.sh asks which profile applies and which skills it leaves unlinked.
        saved = saved_profile(home)
        if args.action == "saved-profile":
            print(saved or "")
        else:
            print("\n".join(unattended.dropped_skills(args.profile or saved)))
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
        steps.install(home, args.skip_external, args.force, herdr_root, args.profile)
    elif args.action == "uninstall":
        steps.uninstall(home, args.skip_external)
