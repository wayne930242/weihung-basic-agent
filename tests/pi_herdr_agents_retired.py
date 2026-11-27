"""pi-straw-boss hosts subagents, so every form of pi-herdr-agents an earlier install left leaves settings and disk."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pi_root import external, resources, steps
from pi_root.pins import PACKAGES
from support.pi import fake_npm_install, run_script

FORK_PIN = "git:github.com/wayne930242/pi-herdr-agents@2045e55da0c7ac52ab41e053992ad12015a9a3c2"
NPM_RELEASE = "npm:pi-herdr-agents@2.0.4"
SB_PIN = next(value for value in PACKAGES if isinstance(value, str) and value.startswith("npm:pi-straw-boss@"))
# pi-straw-boss hosts subagents from 0.110.0 on.
HOST_SINCE = (0, 110, 0)


def source(package):
    return package if isinstance(package, str) else package["source"]


def packages(home):
    return json.loads((home / ".pi/agent/settings.json").read_text()).get("packages", [])


def herdr_entries(home):
    return [package for package in packages(home) if "pi-herdr-agents" in source(package)]


def marker(home):
    return home / ".pi/agent/.weihung-agent-root.json"


class Retired(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.base = Path(self._directory.name)
        self.home = self.base / "home"
        self.agent = self.home / ".pi/agent"
        self.agent.mkdir(parents=True)

    def install(self):
        env = {key: value for key, value in os.environ.items() if key != "PI_HERDR_AGENTS_ROOT"}
        with mock.patch.dict("os.environ", env, clear=True):
            run_script("install.sh", self.home, "--skip-external")

    def test_pi_straw_boss_is_the_only_pinned_subagent_host(self):
        sources = [source(package) for package in PACKAGES]
        self.assertGreaterEqual(tuple(int(part) for part in SB_PIN.rsplit("@", 1)[1].split(".")), HOST_SINCE)
        self.assertFalse([value for value in sources if "pi-herdr-agents" in value])

    def test_an_installed_fork_pin_leaves_settings_for_pi_straw_boss(self):
        (self.agent / "settings.json").write_text(json.dumps({"packages": [FORK_PIN, "npm:pi-straw-boss@0.109.3"]}))
        marker(self.home).write_text(json.dumps({"previous_packages": [], "retired_packages": []}))
        self.install()
        self.assertEqual(herdr_entries(self.home), [])
        self.assertIn(SB_PIN, packages(self.home))
        self.assertTrue((self.agent / "herdr-agents/config.json").is_file())

    def test_the_npm_release_leaves_settings_and_comes_back_on_uninstall(self):
        (self.agent / "settings.json").write_text(json.dumps({"packages": [NPM_RELEASE]}))
        self.install()
        self.assertEqual(herdr_entries(self.home), [])
        run_script("uninstall.sh", self.home, "--skip-external")
        self.assertEqual(herdr_entries(self.home), [NPM_RELEASE])

    def test_a_recorded_override_checkout_leaves_settings(self):
        local = self.base / "pi-herdr-agents"
        local.mkdir()
        (self.agent / "settings.json").write_text(json.dumps({"packages": [str(local), FORK_PIN]}))
        marker(self.home).write_text(json.dumps({"herdr_agents": str(local), "herdr_agents_displaced": [str(self.base / "old")],
                                                 "previous_packages": [], "retired_packages": []}))
        self.install()
        self.assertEqual(herdr_entries(self.home), [])
        state = json.loads(marker(self.home).read_text())
        self.assertNotIn("herdr_agents", state)
        self.assertNotIn("herdr_agents_displaced", state)

    def test_uninstall_removes_a_recorded_override_checkout_no_install_retired(self):
        local = self.base / "pi-herdr-agents"
        local.mkdir()
        (self.agent / "settings.json").write_text(json.dumps({"packages": [str(local)]}))
        marker(self.home).write_text(json.dumps({"herdr_agents": str(local), "previous_packages": []}))
        run_script("uninstall.sh", self.home, "--skip-external")
        self.assertEqual(herdr_entries(self.home), [])

    def test_an_external_install_takes_the_fork_checkout_off_disk(self):
        checkout = self.agent / "git/github.com/wayne930242/pi-herdr-agents"
        checkout.mkdir(parents=True)
        settings = self.agent / "settings.json"
        settings.write_text(json.dumps({"packages": [FORK_PIN]}))
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

        with mock.patch.object(external, "run", fake_run), mock.patch.object(external, "require"), \
                mock.patch.object(resources, "install_statechart"):
            steps.install(self.home, skip_external=False, force=False)
        self.assertFalse(checkout.exists())
        self.assertEqual(herdr_entries(self.home), [])
        self.assertIn(SB_PIN, packages(self.home))


if __name__ == "__main__":
    unittest.main()
