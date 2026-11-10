"""Pi package identity, pin rotation, optional plugins, and the package step."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pi_root import external, packages, steps
from support.pi import fake_npm_install, run_script


class PackageTests(unittest.TestCase):
    def test_package_identity_ignores_the_npm_version(self):
        agent = Path("/unused")
        self.assertEqual(packages.package_id("npm:pi-lens@4.4.7", agent), "npm:pi-lens")
        self.assertEqual(packages.package_id("npm:@scope/name@1.0.0", agent), "npm:@scope/name")
        self.assertEqual(packages.package_id("npm:@scope/name", agent), "npm:@scope/name")
        self.assertEqual(packages.package_id({"source": "npm:pi-lens", "skills": []}, agent), "npm:pi-lens")

    def test_an_aaaav_git_install_gives_way_to_the_npm_package(self):
        earlier = "git:github.com/wayne930242/aaaav"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": [earlier]}))
            (agent / ".weihung-agent-root.json").write_text(json.dumps({"aaaav": earlier}))
            unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
            with mock.patch.dict("os.environ", unset, clear=True):
                run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.13.0"])

    def test_the_pi_aaaav_package_gives_way_to_pi_anchorloop(self):
        earlier = "npm:pi-aaaav@1.3.4"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": [earlier]}))
            (agent / ".weihung-agent-root.json").write_text(json.dumps({"aaaav": earlier}))
            unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
            with mock.patch.dict("os.environ", unset, clear=True):
                run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.13.0"])

    def test_an_aaaav_git_install_the_state_never_recorded_is_removed_too(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": ["git:github.com/wayne930242/aaaav"]}))
            (agent / ".weihung-agent-root.json").write_text(json.dumps({"retired_packages": []}))
            unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
            with mock.patch.dict("os.environ", unset, clear=True):
                run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.13.0"])

    def test_session_hoarder_leaves_a_machine_that_already_installed_it(self):
        hoarder = "npm:@moyai/pi-session-hoarder@0.2.0"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": [hoarder]}))
            # An earlier install recorded its retired packages before the hoarder was retired.
            (agent / ".weihung-agent-root.json").write_text(json.dumps({"retired_packages": []}))
            run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertFalse([item for item in installed if "session-hoarder" in json.dumps(item)], installed)

    def test_straw_boss_git_installs_give_way_to_the_npm_package(self):
        for earlier in ("git:github.com/wayne930242/straw-boss", "git:github.com/wayne930242/straw-boss@old-commit"):
            with self.subTest(earlier=earlier), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = home / ".pi/agent"
                agent.mkdir(parents=True)
                (agent / "settings.json").write_text(json.dumps({"packages": [earlier]}))
                run_script("install.sh", home, "--skip-external")
                installed = json.loads((agent / "settings.json").read_text())["packages"]
                straw = [item for item in installed if "straw-boss" in item]
                self.assertEqual(len(straw), 1, straw)
                self.assertTrue(straw[0].startswith("npm:pi-straw-boss@"), straw)

    def test_a_root_variable_swaps_the_latest_commit_for_a_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            with mock.patch.dict("os.environ", {"PI_ANCHORLOOP_ROOT": str(checkout)}):
                with self.assertRaisesRegex(ValueError, "has no package.json"):
                    packages.anchorloop_source()
                (checkout / "package.json").write_text("{}")
                self.assertEqual(packages.anchorloop_source(), str(checkout.resolve()))
        unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
        with mock.patch.dict("os.environ", unset, clear=True):
            self.assertEqual(packages.anchorloop_source(), "npm:pi-anchorloop@2.13.0")

    def test_leaving_a_checkout_override_removes_the_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            checkout = Path(directory) / "anchorloop"
            checkout.mkdir()
            (checkout / "package.json").write_text("{}")
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text("{}")
            run_script("install.sh", home, "--skip-external", env={"PI_ANCHORLOOP_ROOT": str(checkout)})
            first = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertNotIn("npm:pi-anchorloop@2.13.0", first)
            self.assertTrue(any("anchorloop" in item for item in first), first)
            unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
            with mock.patch.dict("os.environ", unset, clear=True):
                run_script("install.sh", home, "--skip-external")
            second = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertEqual([item for item in second if "anchorloop" in item], ["npm:pi-anchorloop@2.13.0"])

    def test_previous_git_bridge_revision_is_restored(self):
        old = "git:github.com/wayne930242/pi-claude-bridge@old-commit"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": [old, "npm:user-package"]}))
            run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertNotIn(old, installed)
            self.assertEqual(sum("pi-claude-bridge" in item for item in installed), 1)
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(json.loads((agent / "settings.json").read_text())["packages"], [old, "npm:user-package"])

    def test_optional_plugins_are_managed_when_present_and_skipped_when_absent(self):
        variables = {"alpha": "PI_ALPHA_ROOT", "beta": "PI_BETA_ROOT"}
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            roots = {name: home / "checkouts" / name for name in variables}
            for root in roots.values():
                root.mkdir(parents=True)
                (root / "package.json").write_text("{}")
            overlay = home / "overlay"
            overlay.mkdir()
            (overlay / "overlay.json").write_text(json.dumps({"plugins": {name: {"name": name, "variable": variable, "path": "../none"} for name, variable in variables.items()}}))
            env = {"WEIHUNG_OVERLAY": str(overlay), **{variable: str(roots[name]) for name, variable in variables.items()}}
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            for _ in range(2):
                run_script("install.sh", home, "--skip-external", env=env)
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            for root in roots.values():
                self.assertEqual(installed.count(str(root.resolve())), 1)
            # The checkout goes away: the next install drops the entry instead of leaving Pi a missing package.
            (roots["beta"] / "package.json").unlink()
            result = run_script("install.sh", home, "--skip-external", env=env)
            self.assertIn("beta not found", result.stderr)
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertNotIn(str(roots["beta"].resolve()), installed)
            self.assertIn(str(roots["alpha"].resolve()), installed)
            run_script("uninstall.sh", home, "--skip-external", env=env)
            settings = agent / "settings.json"
            remaining = json.loads(settings.read_text()).get("packages", []) if settings.exists() else []
            self.assertFalse([item for item in remaining if "checkouts" in str(item)])
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            overlay = home / "overlay"
            overlay.mkdir()
            (overlay / "overlay.json").write_text(json.dumps({"plugins": {name: {"name": name, "variable": variable, "path": "../none"} for name, variable in variables.items()}}))
            env = {"WEIHUNG_OVERLAY": str(overlay), **{variable: str(home / "missing" / name) for name, variable in variables.items()}}
            result = run_script("install.sh", home, "--skip-external", env=env)
            self.assertIn("alpha not found", result.stderr)
            self.assertIn("beta not found", result.stderr)
            installed = json.loads((home / ".pi/agent/settings.json").read_text())["packages"]
            self.assertFalse([item for item in installed if "checkouts" in str(item) or "/missing/" in str(item)])

    def test_external_git_switch_keeps_the_new_checkout(self):
        old = "git:github.com/wayne930242/pi-claude-bridge@old-commit"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            settings = agent / "settings.json"
            settings.write_text(json.dumps({"packages": [old]}))
            removals = []

            def fake_run(args, _home):
                if args[0] == "npm":
                    fake_npm_install(args)
                if args[:2] == ["pi", "install"]:
                    current = json.loads(settings.read_text())
                    current.setdefault("packages", []).append(args[2])
                    settings.write_text(json.dumps(current))
                if args[:2] == ["pi", "remove"]:
                    removals.append(args[2])

            with mock.patch.object(external, "run", fake_run), mock.patch.object(external, "require"):
                steps.install(home, skip_external=False, force=False)
            self.assertNotIn(old, json.loads(settings.read_text())["packages"])
            self.assertNotIn(old, removals)

    def test_external_install_takes_retired_packages_off_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            (agent / "npm").mkdir(parents=True)
            (agent / "npm/package.json").write_text(json.dumps({"dependencies": {"pi-phoenix-otel": "^0.2.0", "pi-intercom": "^0.18.0"}}))
            quotas = agent / "git/github.com/wayne930242/pi-quotas"
            quotas.mkdir(parents=True)
            settings = agent / "settings.json"
            settings.write_text(json.dumps({"packages": []}))
            uninstalled = []

            def fake_run(args, _home):
                if args[:2] == ["npm", "uninstall"]:
                    uninstalled.append(args[2:])
                elif args[0] == "npm":
                    fake_npm_install(args)
                if args[:2] == ["pi", "install"]:
                    current = json.loads(settings.read_text())
                    current.setdefault("packages", []).append(args[2])
                    settings.write_text(json.dumps(current))

            with mock.patch.object(external, "run", fake_run), mock.patch.object(external, "require"):
                steps.install(home, skip_external=False, force=False)
            self.assertEqual(uninstalled, [["pi-phoenix-otel", "--prefix", str(agent / "npm"), "--legacy-peer-deps"]])
            self.assertFalse(quotas.exists())

    def test_the_unattended_profile_filters_owned_packages_by_name_not_version(self):
        from pi_root.pins import PACKAGES, UNATTENDED_DROPS
        default = packages.owned_packages({})
        headless = packages.owned_packages({"profile": "unattended"})
        self.assertEqual(default, PACKAGES)
        self.assertEqual([p for p in PACKAGES if p not in headless], packages.profile_dropped({"profile": "unattended"}))
        self.assertEqual(len(PACKAGES) - len(headless), len(UNATTENDED_DROPS), "every drop names a pinned package")
        self.assertEqual(packages.profile_dropped({}), [])

    def fake_install_run(self, settings: Path, removed: list[str]):
        def fake_run(args, _home):
            if args[0] == "npm":
                fake_npm_install(args)
            if args[:2] == ["git", "clone"]:
                Path(args[-1]).joinpath(".git").mkdir(parents=True)
            if args[:2] == ["pi", "install"]:
                current = json.loads(settings.read_text()) if settings.exists() else {}
                current.setdefault("packages", []).append(args[2])
                settings.parent.mkdir(parents=True, exist_ok=True)
                settings.write_text(json.dumps(current))
            if args[:2] == ["pi", "remove"]:
                removed.append(args[2])
                current = json.loads(settings.read_text())
                current["packages"] = [value for value in current["packages"] if value != args[2]]
                settings.write_text(json.dumps(current))
        return fake_run

    def assert_ttt_without_pi_skills(self, home: Path):
        agent = home / ".pi/agent"
        marker = json.loads((agent / ".weihung-agent-root.json").read_text())
        self.assertTrue((home / ".local/bin/ttt").is_symlink(), "ttt stays for Linear on an unattended computer")
        self.assertTrue((agent / "skills/managing-linear-tasks/SKILL.md").is_file())
        self.assertFalse((agent / "skills/pi-skills").exists() or (agent / "skills/pi-skills").is_symlink())
        self.assertFalse((home / ".local/share/weihung-agent-root/pi-skills").exists())
        self.assertNotIn("pi_skills_clone", marker)
        self.assertIn("ttt_prefix", marker)
        self.assertNotIn(".pi/agent/skills/pi-skills", marker["ported_resources"])

    def test_switching_to_unattended_removes_the_dropped_packages_and_pi_skills_but_keeps_ttt(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".pi/agent/settings.json"
            removed = []
            with mock.patch.object(external, "run", self.fake_install_run(settings, removed)), \
                    mock.patch.object(external, "require"), mock.patch.object(external, "capture", lambda *_: ""):
                steps.install(home, skip_external=False, force=False)
                self.assertTrue((home / ".pi/agent/skills/pi-skills").is_symlink())
                steps.install(home, skip_external=False, force=False, profile="unattended")
            self.assertIn("npm:cc-safety-net@2.7.8", removed)
            self.assertNotIn("npm:pi-robot-hand@0.7.2", json.loads(settings.read_text())["packages"])
            self.assert_ttt_without_pi_skills(home)

    def test_a_fresh_unattended_install_brings_ttt_and_no_pi_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".pi/agent/settings.json"
            with mock.patch.object(external, "run", self.fake_install_run(settings, [])), \
                    mock.patch.object(external, "require"), mock.patch.object(external, "capture", lambda *_: ""):
                steps.install(home, skip_external=False, force=False, profile="unattended")
                steps.install(home, skip_external=False, force=False, profile="unattended")
            self.assert_ttt_without_pi_skills(home)

    def test_an_external_install_without_herdr_on_path_fails_before_installing_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            calls = []
            with mock.patch.object(external, "run", lambda args, _home: calls.append(args)), \
                    mock.patch.dict(os.environ, {"PATH": str(home)}):
                with self.assertRaisesRegex(ValueError, "herdr is not on PATH"):
                    steps.install(home, skip_external=False, force=False)
            self.assertEqual(calls, [])

    def test_team_toon_tack_installs_its_pinned_version_and_the_pin_tool_tracks_it(self):
        import importlib.util
        from pi_root import resources
        from pi_root.pins import TEAM_TOON_TACK
        self.assertRegex(TEAM_TOON_TACK, r"^team-toon-tack@\d+\.\d+\.\d+$")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            calls = []

            def fake_run(args, _home):
                calls.append(args)
                fake_npm_install(args)

            with mock.patch.object(external, "run", fake_run):
                resources.install_ttt(home, {}, force=False)
        self.assertEqual([args[-1] for args in calls if args[:2] == ["npm", "install"]], [TEAM_TOON_TACK])
        spec = importlib.util.spec_from_file_location("pi_pins", Path(__file__).resolve().parents[1] / "scripts/pi-pins.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn("team-toon-tack", [pin.name for pin in module.collect_pins()])

    def test_the_update_schedule_refuses_outside_macos(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pi_pins", Path(__file__).resolve().parents[1] / "scripts/pi-pins.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module.sys, "platform", "linux"):
            with self.assertRaisesRegex(ValueError, "provisioning playbook"):
                module.schedule()


if __name__ == "__main__":
    unittest.main()
