"""The unattended profile installs the tower-mode command and the rule that runs it; no other profile does."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from support.pi import ROOT, run_script

SCRIPT = ROOT / "scripts/tower-mode.mjs"


class TowerModeInstallTests(unittest.TestCase):
    def test_only_the_unattended_profile_links_the_command_and_a_switch_takes_it_back_out(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            link = home / ".local/bin/tower-mode"
            marker = home / ".pi/agent/.weihung-agent-root.json"
            run_script("install.sh", home, "--skip-external", "--no-overlay")
            self.assertFalse(link.exists() or link.is_symlink(), "the default profile does not install it")

            run_script("install.sh", home, "--skip-external", "--no-overlay", "--profile", "unattended")
            self.assertEqual(link.readlink(), SCRIPT)
            self.assertTrue(os.access(SCRIPT, os.X_OK), "the script is executable")
            self.assertIn(".local/bin/tower-mode", json.loads(marker.read_text())["ported_resources"])

            run_script("install.sh", home, "--skip-external", "--no-overlay")
            self.assertTrue(link.is_symlink(), "a bare run keeps the profile and the link")

            run_script("install.sh", home, "--skip-external", "--no-overlay", "--profile", "default")
            self.assertFalse(link.exists() or link.is_symlink(), "--profile default takes it back out")
            self.assertNotIn(".local/bin/tower-mode", json.loads(marker.read_text()).get("ported_resources", {}))

    def test_uninstall_removes_the_link_and_a_user_file_there_needs_force(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            link = home / ".local/bin/tower-mode"
            link.parent.mkdir(parents=True)
            link.write_text("mine\n")
            refused = run_script("install.sh", home, "--skip-external", "--no-overlay", "--profile", "unattended", check=False)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(link.read_text(), "mine\n")

            run_script("install.sh", home, "--skip-external", "--no-overlay", "--profile", "unattended", "--force")
            self.assertEqual(link.readlink(), SCRIPT)
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(link.read_text(), "mine\n", "uninstall puts the user's file back")

    def test_the_installed_command_runs_and_claims_nothing_it_cannot_justify(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_script("install.sh", home, "--skip-external", "--no-overlay", "--profile", "unattended")
            state = home / ".local/state/agent-tower/tower-mode.json"
            state.parent.mkdir(parents=True)
            state.write_text("{")
            token = home / "token"
            token.write_text("mpbox_x\n")
            env = {"PATH": os.environ["PATH"], "HOME": str(home), "TOWER_MODE_TOKEN_FILE": str(token),
                   "TOWER_MODE_URL": "http://127.0.0.1:1/mode"}
            result = subprocess.run([str(home / ".local/bin/tower-mode")], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, 'mode=unknown claim=no read=file board="tower-mode file unreadable"\n')


class TowerModeRuleTests(unittest.TestCase):
    def test_the_unattended_rule_runs_the_command_before_each_claim_and_each_new_train(self):
        text = (ROOT / "pi/AGENTS.unattended.md.in").read_text()
        self.assertIn("`tower-mode`", text)
        self.assertIn("claim=no", text)
        self.assertIn("before each claim", text)
        self.assertIn("new train", text)
        self.assertNotIn("tower-mode", (ROOT / "pi/AGENTS.md.in").read_text())


if __name__ == "__main__":
    unittest.main()
