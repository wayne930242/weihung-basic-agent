"""The small managed settings: mcp-adapter and pi's built-in MCP."""

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hashlib

from pi_root import configs
from support.pi import ROOT, run_script


class ConfigTests(unittest.TestCase):
    def test_mcp_config_is_the_adapter_file_and_leaves_pi_mcp_json_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = Path(directory) / ".pi/agent"
            agent.mkdir(parents=True)
            self.assertEqual(configs.mcp_config_path(agent), agent / "mcp-adapter.json")
            (agent / "mcp.json").write_text('{"mcpServers": {"user": {}}}')
            self.assertEqual(configs.mcp_config_path(agent), agent / "mcp-adapter.json")
            self.assertEqual((agent / "mcp.json").read_text(), '{"mcpServers": {"user": {}}}')
            self.assertFalse((agent / "mcp-adapter.json").exists())

    def test_builtin_mcp_is_disabled_for_the_adapter_and_restored(self):
        for before in (None, ["extra.ts"], ["-builtin:mcp"]):
            with self.subTest(before=before), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = home / ".pi/agent"
                agent.mkdir(parents=True)
                settings = agent / "settings.json"
                settings.write_text(json.dumps({} if before is None else {"extensions": before}))
                run_script("install.sh", home, "--skip-external")
                installed = json.loads(settings.read_text())["extensions"]
                self.assertEqual(installed.count("-builtin:mcp"), 1, installed)
                self.assertEqual([item for item in installed if item != "-builtin:mcp"], [item for item in before or [] if item != "-builtin:mcp"])
                run_script("install.sh", home, "--skip-external")
                self.assertEqual(json.loads(settings.read_text())["extensions"], installed)
                run_script("uninstall.sh", home, "--skip-external")
                self.assertEqual(json.loads(settings.read_text()).get("extensions"), before)

    def test_retired_computer_use_config_gets_back_what_an_earlier_install_replaced(self):
        # (file before the earlier install, or None when it had none)
        for before in (None, {"browser_use": False}, {"headless": False, "cursor_overlay": True}):
            with self.subTest(before=before), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = home / ".pi/agent"
                path = agent / "extensions/pi-computer-use.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({**(before or {}), "headless": True}))
                marker = agent / ".weihung-agent-root.json"
                marker.write_text(json.dumps({
                    "previous_computer_use": {"headless": (before or {}).get("headless")},
                    "previous_computer_use_present": ["headless"] if before and "headless" in before else [],
                    "installed_computer_use": {"headless": True},
                    "previous_computer_use_file_present": before is not None}))
                run_script("install.sh", home, "--skip-external", "--force")
                if before is None:
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(json.loads(path.read_text()), before)
                self.assertFalse([key for key in json.loads(marker.read_text()) if "computer_use" in key])
                run_script("install.sh", home, "--skip-external")
                self.assertEqual(path.exists(), before is not None, "a later install leaves the file alone")

    def test_a_fresh_install_writes_no_computer_use_config(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_script("install.sh", home, "--skip-external")
            self.assertFalse((home / ".pi/agent/extensions/pi-computer-use.json").exists())
            self.assertTrue((home / ".agents/skills/agent-desktop").is_symlink())

    def test_research_hub_is_not_registered_and_an_earlier_install_entry_is_retired(self):
        earlier = {"command": "npx", "args": ["-y", "thesis-toolkit@0.1.3", "mcp", "research-hub"]}
        user_entry = {"command": "my-research-hub"}
        edited = {"command": "edited-research-hub"}
        # (entry the earlier install replaced, entry in the file now, entry expected after install and after uninstall)
        cases = ((None, None, None), (None, earlier, None), (user_entry, earlier, user_entry), (None, edited, edited))
        for previous, current, expected in cases:
            with self.subTest(previous=previous, current=current), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = home / ".pi/agent"
                agent.mkdir(parents=True)
                path = agent / "mcp-adapter.json"
                if current is not None:
                    path.write_text(json.dumps({"mcpServers": {configs.RESEARCH_HUB: current}}))
                    (agent / ".weihung-agent-root.json").write_text(json.dumps(
                        {"installed_research_hub_server": earlier, "previous_research_hub_server": previous}))
                run_script("install.sh", home, "--skip-external", "--force")
                self.assertEqual(json.loads(path.read_text())["mcpServers"].get(configs.RESEARCH_HUB), expected)
                marker = json.loads((agent / ".weihung-agent-root.json").read_text())
                self.assertFalse({"installed_research_hub_server", "previous_research_hub_server"} & set(marker), marker)
                run_script("uninstall.sh", home, "--skip-external")
                restored = json.loads(path.read_text()).get("mcpServers", {}) if path.exists() else {}
                self.assertEqual(restored.get(configs.RESEARCH_HUB), expected)

    def test_uninstall_after_an_install_that_registered_research_hub_restores_the_user_entry(self):
        earlier = {"command": "npx", "args": ["-y", "thesis-toolkit@0.1.3", "mcp", "research-hub"]}
        user_entry = {"command": "my-research-hub"}
        for previous in (None, user_entry):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = home / ".pi/agent"
                agent.mkdir(parents=True)
                path = agent / "mcp-adapter.json"
                path.write_text(json.dumps({"mcpServers": {configs.RESEARCH_HUB: earlier, "other": {"command": "x"}}}))
                (agent / ".weihung-agent-root.json").write_text(json.dumps(
                    {"installed_research_hub_server": earlier, "previous_research_hub_server": previous}))
                run_script("uninstall.sh", home, "--skip-external")
                self.assertEqual(json.loads(path.read_text())["mcpServers"].get(configs.RESEARCH_HUB), previous)



class HerdrModelsTests(unittest.TestCase):
    def setUp(self):
        self.repo_models = json.loads((ROOT / "pi/herdr-agents-models.json").read_text())
        self.unattended_models = json.loads((ROOT / "pi/herdr-agents-models.unattended.json").read_text())
        self.host_models = deepcopy(self.unattended_models)
        self.host_models["agents"]["worker"] = "openai-codex/gpt-6.2-astra"
        self.host_models["tasks"]["coding"] = ["openai-codex/gpt-6.2-astra"]

    def test_models_follow_the_repository_file_and_uninstall_restores_the_previous_value(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".pi/agent/herdr-agents/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"models": {"default": "user/model"}, "other": True}))
            run_script("install.sh", home, "--skip-external", "--force")
            self.assertEqual(json.loads(config.read_text())["models"], self.repo_models)
            run_script("install.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text())["models"], self.repo_models)
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text()), {"models": {"default": "user/model"}, "other": True})

    def test_a_fresh_config_gets_the_status_section_the_subagent_host_requires(self):
        # weihung-agent-root#1: a config.json without `status` stopped pi-herdr-agents from loading; pi-straw-boss's host reads the same file.
        user_status = {"enabled": False}
        for before in (None, {"other": True}, {"status": user_status}):
            with self.subTest(before=before), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                config = home / ".pi/agent/herdr-agents/config.json"
                if before is not None:
                    config.parent.mkdir(parents=True)
                    config.write_text(json.dumps(before))
                run_script("install.sh", home, "--skip-external")
                installed = json.loads(config.read_text())
                self.assertEqual(installed["status"], user_status if before and "status" in before else configs.HERDR_STATUS)
                run_script("install.sh", home, "--skip-external")
                self.assertEqual(json.loads(config.read_text()), installed)
                run_script("uninstall.sh", home, "--skip-external")
                self.assertEqual(json.loads(config.read_text()) if config.exists() else None, before)

    def test_a_hand_edit_since_install_stops_the_next_install(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_script("install.sh", home, "--skip-external")
            config = home / ".pi/agent/herdr-agents/config.json"
            edited = json.loads(config.read_text())
            edited["models"]["agents"]["reviewer"] = "user/edited"
            config.write_text(json.dumps(edited))
            failed = run_script("install.sh", home, "--skip-external", check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("herdr-agents-models.json", failed.stderr)
            self.assertEqual(json.loads(config.read_text())["models"]["agents"]["reviewer"], "user/edited")
            run_script("install.sh", home, "--skip-external", "--force")
            self.assertEqual(json.loads(config.read_text())["models"], self.repo_models)

    def test_models_file_is_remembered_and_does_not_allow_hand_edits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".pi/agent/herdr-agents/config.json"
            source = home / "host models.json"
            source.write_text(json.dumps(self.host_models))
            run_script("install.sh", home, "--skip-external", "--profile", "unattended", "--models-file", str(source))
            self.assertEqual(json.loads(config.read_text())["models"], self.host_models)
            run_script("install.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text())["models"], self.host_models)

            updated = deepcopy(self.host_models)
            updated["agents"]["reviewer"] = "user/updated"
            source.write_text(json.dumps(updated))
            run_script("install.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text())["models"], updated, "a bare install re-reads the file")

            edited = json.loads(config.read_text())
            edited["models"]["agents"]["reviewer"] = "user/edited"
            config.write_text(json.dumps(edited))
            failed = run_script("install.sh", home, "--skip-external", check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(str(source), failed.stderr)
            self.assertIn("differs from", failed.stderr)
            self.assertEqual(json.loads(config.read_text()), edited)
            refused = run_script("install.sh", home, "--skip-external", "--no-models-file", check=False)
            self.assertNotEqual(refused.returncode, 0, "clearing the override does not bypass edit detection")
            run_script("install.sh", home, "--skip-external", "--force")
            self.assertEqual(json.loads(config.read_text())["models"], updated, "a refused clear keeps the remembered path")

    def test_models_file_switch_clear_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".pi/agent/herdr-agents/config.json"
            config.parent.mkdir(parents=True)
            before = {"models": {"default": "user/model"}, "other": True}
            config.write_text(json.dumps(before))
            first = home / "first.json"
            first.write_text(json.dumps(self.host_models))
            second = home / "second.json"
            second_models = deepcopy(self.host_models)
            second_models["tasks"]["coding"].append("openrouter/vendor/model:free")
            second.write_text(json.dumps(second_models))

            run_script("install.sh", home, "--skip-external", "--profile", "unattended", "--force")
            run_script("install.sh", home, "--skip-external", "--models-file", str(first))
            self.assertEqual(json.loads(config.read_text())["models"], self.host_models)
            run_script("install.sh", home, "--skip-external", "--models-file", str(second))
            self.assertEqual(json.loads(config.read_text())["models"], second_models)
            second.unlink()
            failed = run_script("install.sh", home, "--skip-external", check=False)
            self.assertNotEqual(failed.returncode, 0, "missing remembered files must not fall back silently")
            self.assertIn(str(second), failed.stderr)
            self.assertEqual(json.loads(config.read_text())["models"], second_models)
            run_script("install.sh", home, "--skip-external", "--no-models-file")
            run_script("install.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text())["models"], self.unattended_models)

            run_script("install.sh", home, "--skip-external", "--models-file", str(first))
            first.unlink()
            run_script("uninstall.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text()), before)

    def test_invalid_models_file_stops_before_install_writes(self) -> None:
        cases = (
            (None, "does not exist"),
            ("{", "not valid JSON"),
            ("[]", "default, agents, tasks"),
            (json.dumps({"default": "user/model", "agents": {}}), "default, agents, tasks"),
            (json.dumps({**self.host_models, "default": "task:coding"}), "default must be an exact provider/model ID"),
            (json.dumps({**self.host_models, "agents": []}), "agents must be an object"),
            (json.dumps({**self.host_models, "agents": {"workr": "user/model"}}), "agents.workr is not a supported role"),
            (json.dumps({**self.host_models, "agents": {"worker": "user/one,user/two"}}), "agents.worker must be an exact provider/model ID"),
            (json.dumps({**self.host_models, "tasks": {"coding": "user/model"}}), "tasks.coding must be a nonempty array"),
            (json.dumps({**self.host_models, "tasks": {"coding": []}}), "tasks.coding must be a nonempty array"),
            (json.dumps({**self.host_models, "tasks": {"coding": ["user/*"]}}), "tasks.coding[0] must be an exact provider/model ID"),
            (json.dumps({**self.host_models, "tasks": {"codign": ["user/model"]}}), "tasks.codign is not a supported task category"),
            (json.dumps({**self.host_models, "tasks": {"coding": ["user/model", "user/model"]}}), "tasks.coding contains duplicate model IDs"),
        )
        for text, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                source = home / "models.json"
                if text is not None:
                    source.write_text(text)
                failed = run_script("install.sh", home, "--skip-external", "--models-file", str(source), check=False)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn(str(source), failed.stderr)
                self.assertIn(message, failed.stderr)
                self.assertFalse((home / ".agents").exists())
                self.assertFalse((home / ".pi").exists())

    def test_the_unattended_profile_writes_its_own_models_without_fable(self):
        unattended_models = self.unattended_models
        self.assertEqual(unattended_models.keys(), self.repo_models.keys())
        self.assertEqual(unattended_models["agents"].keys(), self.repo_models["agents"].keys())
        self.assertEqual(unattended_models["tasks"].keys(), self.repo_models["tasks"].keys())
        self.assertNotIn("fable", json.dumps(unattended_models))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".pi/agent/herdr-agents/config.json"
            run_script("install.sh", home, "--skip-external", "--profile", "unattended")
            self.assertEqual(json.loads(config.read_text())["models"], unattended_models)
            run_script("install.sh", home, "--skip-external")
            self.assertEqual(json.loads(config.read_text())["models"], unattended_models, "a bare run keeps the profile")
            run_script("install.sh", home, "--skip-external", "--profile", "default")
            self.assertEqual(json.loads(config.read_text())["models"], self.repo_models)


class RemovedModelProfileTests(unittest.TestCase):
    """The model strategy profile was removed on 2026-10-03; models live in pi/herdr-agents-models.json."""

    def test_the_profile_does_not_come_back(self):
        for relative in ("skills/managing-model-preferences", "pi/model-profiles.json", "scripts/pi_root/profile.py",
                         "pi/extensions/tier-roles.ts"):
            self.assertFalse((ROOT / relative).exists(), relative)
        self.assertNotIn("tier-roles", (ROOT / "package.json").read_text())
        self.assertNotIn("apply-profile", (ROOT / "scripts/pi_root/cli.py").read_text())
        template = (ROOT / "pi/AGENTS.md.in").read_text()
        for word in ("managing-model-preferences", "model strategy", "tier"):
            self.assertNotIn(word, template)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_script("install.sh", home, "--skip-external")
            self.assertFalse((home / ".pi/agent/herdr-agents/roles").exists())
            self.assertFalse((home / ".agents/skills/managing-model-preferences").exists())

if __name__ == "__main__":
    unittest.main()
