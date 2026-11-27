"""The pi-target.py command line."""

import argparse
import os
from pathlib import Path

from . import configs, steps, unattended
from .jsonfile import read_json
from .paths import MARKER, OVERLAY_VARIABLE, saved_overlay, saved_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "install-preflight", "install", "uninstall", "saved-overlay", "saved-profile", "dropped-skills"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-overlay", action="store_true", help="install without the overlay the last install recorded")
    parser.add_argument("--profile", choices=unattended.PROFILES, help="install profile; a run without it keeps the recorded one")
    models = parser.add_mutually_exclusive_group()
    models.add_argument("--models-file", type=Path, metavar="PATH", help="host models file; a run without it keeps the recorded path")
    models.add_argument("--no-models-file", action="store_true", help="clear the recorded models file and use the profile's shared models")
    args = parser.parse_args()
    if (args.models_file or args.no_models_file) and args.action not in ("install", "install-preflight"):
        parser.error("--models-file and --no-models-file are install options")
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
    try:
        if args.action == "install-preflight":
            configs.load_models_override(read_json(home / MARKER), args.models_file, args.no_models_file)
        elif args.action == "install":
            steps.install(home, args.skip_external, args.force, args.profile,
                          models_file=args.models_file, no_models_file=args.no_models_file)
        elif args.action == "uninstall":
            steps.uninstall(home, args.skip_external)
    except ValueError as error:
        parser.exit(1, f"Error: {error}\n")
