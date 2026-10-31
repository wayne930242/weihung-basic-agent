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
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.3.0"])

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
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.3.0"])

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
            self.assertEqual([item for item in installed if "aaaav" in item or "anchorloop" in item], ["npm:pi-anchorloop@2.3.0"])

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
            self.assertEqual(packages.anchorloop_source(), "npm:pi-anchorloop@2.3.0")

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
            self.assertNotIn("npm:pi-anchorloop@2.3.0", first)
            self.assertTrue(any("anchorloop" in item for item in first), first)
            unset = {key: value for key, value in os.environ.items() if key != "PI_ANCHORLOOP_ROOT"}
            with mock.patch.dict("os.environ", unset, clear=True):
                run_script("install.sh", home, "--skip-external")
            second = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertEqual([item for item in second if "anchorloop" in item], ["npm:pi-anchorloop@2.3.0"])

    def test_retired_theme_package_is_replaced_and_restored(self):
        old = {"source": "npm:@victor-software-house/pi-curated-themes@0.2.1", "themes": ["themes/catppuccin-mocha.json"], "skills": []}
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": [old, "npm:user-package"]}))
            run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertNotIn(old, installed)
            self.assertIn({"source": "npm:@sherif-fanous/pi-catppuccin@0.3.0", "themes": ["themes/catppuccin-mocha.json"]}, installed)
            self.assertIn("npm:user-package", installed)
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(json.loads((agent / "settings.json").read_text())["packages"], [old, "npm:user-package"])

    def test_merged_secret_drop_package_is_removed_and_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            (agent / "settings.json").write_text(json.dumps({"packages": ["npm:pi-secret-drop@0.1.6", "npm:user-package"]}))
            run_script("install.sh", home, "--skip-external")
            installed = json.loads((agent / "settings.json").read_text())["packages"]
            self.assertNotIn("npm:pi-secret-drop@0.1.6", installed)
            self.assertTrue(any(isinstance(p, str) and p.startswith("npm:pi-robot-hand@") for p in installed), installed)
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(json.loads((agent / "settings.json").read_text())["packages"], ["npm:pi-secret-drop@0.1.6", "npm:user-package"])

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

    def test_upgrade_pins_unpinned_packages_and_reads_an_old_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agent = home / ".pi/agent"
            agent.mkdir(parents=True)
            settings = agent / "settings.json"
            settings.write_text(json.dumps({"packages": ["npm:user-package"]}))
            run_script("install.sh", home, "--skip-external")
            # Reproduce the unpinned packages and marker an install before pinning left behind.
            marker = agent / ".weihung-agent-root.json"
            state = json.loads(marker.read_text())
            state["previous_ui_settings"] = {name: value for name, value in state["previous_ui_settings"].items()
                                             if name != "enableInstallTelemetry"}
            state.pop("previous_ui_settings_present")
            marker.write_text(json.dumps(state))
            current = json.loads(settings.read_text())
            current["packages"] = ["npm:user-package", "npm:pi-lens", "npm:pi-web-access@0.31.0"]
            current.pop("enableInstallTelemetry")
            settings.write_text(json.dumps(current))
            run_script("install.sh", home, "--skip-external")
            upgraded = json.loads(settings.read_text())
            sources = [item["source"] if isinstance(item, dict) else item for item in upgraded["packages"]]
            self.assertEqual([item for item in sources if "pi-lens" in item], ["git:github.com/wayne930242/pi-lens@96ccbc4d16fce06956bec621a7ff327e1c8545cb"])
            self.assertEqual([item for item in sources if "pi-web-access" in item], [], "a retired package is removed")
            self.assertIs(upgraded["enableInstallTelemetry"], False)
            run_script("uninstall.sh", home, "--skip-external")
            restored = json.loads(settings.read_text())
            self.assertEqual(restored["packages"], ["npm:user-package"])
            self.assertNotIn("enabledModels", restored)
            self.assertNotIn("enableInstallTelemetry", restored)

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

            with mock.patch.object(external, "run", fake_run):
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

            with mock.patch.object(external, "run", fake_run):
                steps.install(home, skip_external=False, force=False)
            self.assertEqual(uninstalled, [["pi-phoenix-otel", "--prefix", str(agent / "npm"), "--legacy-peer-deps"]])
            self.assertFalse(quotas.exists())


if __name__ == "__main__":
    unittest.main()
