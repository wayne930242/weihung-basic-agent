"""An overlay checkout layered over this one: its skills, instruction additions, and the stale links of an earlier layout."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from support.pi import ROOT, run_script


def make_overlay(base: Path, skills: tuple[str, ...] = ("extra-skill",)) -> Path:
    overlay = base / "overlay"
    for name in skills:
        (overlay / "skills" / name).mkdir(parents=True)
        (overlay / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill\n---\n")
    (overlay / "pi").mkdir(parents=True, exist_ok=True)
    (overlay / "pi/AGENTS.append.md").write_text("## Overlay\n\nOverlay-only instruction.\n")
    return overlay


class OverlayTests(unittest.TestCase):
    def test_overlay_skills_and_instructions_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            overlay = make_overlay(base)
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            self.assertEqual((home / ".agents/skills/extra-skill").readlink(), overlay.resolve() / "skills/extra-skill")
            self.assertEqual((home / ".agents/skills/going-to-sleep").readlink(), ROOT / "skills/going-to-sleep")
            text = (home / ".pi/agent/AGENTS.md").read_text()
            self.assertIn("Overlay-only instruction.", text)
            self.assertIn("## Model and dispatch", text)
            # A rerun changes nothing, and dropping the overlay's skill prunes its link.
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            (overlay / "skills/extra-skill/SKILL.md").unlink()
            (overlay / "skills/extra-skill").rmdir()
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            self.assertFalse((home / ".agents/skills/extra-skill").is_symlink())
            run_script("uninstall.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            self.assertFalse((home / ".pi/agent/AGENTS.md").exists())
            self.assertFalse((home / ".agents/skills/going-to-sleep").exists())

    def test_overlay_model_providers_merge_into_models_json_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            overlay = make_overlay(base)
            mine = {"baseUrl": "https://example.test/v1", "api": "openai-completions", "models": [{"id": "m"}]}
            (overlay / "pi/models.json").write_text(json.dumps({"providers": {"mine": mine}}))
            models = home / ".pi/agent/models.json"
            models.parent.mkdir(parents=True)
            user = {"baseUrl": "http://localhost:11434/v1", "api": "openai-completions", "models": [{"id": "x"}]}
            models.write_text(json.dumps({"providers": {"ollama": user}}))
            env = {"WEIHUNG_OVERLAY": ""}
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            self.assertEqual(json.loads(models.read_text())["providers"], {"ollama": user, "mine": mine})
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            # A hand edit of a managed provider stops the next install.
            edited = json.loads(models.read_text())
            edited["providers"]["mine"]["baseUrl"] = "https://elsewhere.test/v1"
            models.write_text(json.dumps(edited))
            with self.assertRaises(Exception):
                run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            models.write_text(json.dumps({"providers": {"ollama": user, "mine": mine}}))
            # Dropping the provider from the overlay removes it; the user's provider stays.
            (overlay / "pi/models.json").write_text(json.dumps({"providers": {}}))
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            self.assertEqual(json.loads(models.read_text())["providers"], {"ollama": user})
            (overlay / "pi/models.json").write_text(json.dumps({"providers": {"mine": mine}}))
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            run_script("uninstall.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            self.assertEqual(json.loads(models.read_text())["providers"], {"ollama": user})

    def test_a_later_run_without_an_overlay_keeps_the_recorded_one(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            overlay = make_overlay(base)
            plugin = base / "plugin"
            plugin.mkdir()
            (plugin / "package.json").write_text("{}")
            (overlay / "overlay.json").write_text(json.dumps({"plugins": {"gamma": {"name": "gamma", "variable": "PI_GAMMA_ROOT", "path": "../plugin"}}}))
            env = {"WEIHUNG_OVERLAY": "", "PI_GAMMA_ROOT": str(plugin)}
            agent = home / ".pi/agent"
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env=env)
            self.assertEqual(json.loads((agent / ".weihung-agent-root.json").read_text())["overlay"], str(overlay.resolve()))
            before = (agent / "AGENTS.md").read_text()
            settings = json.loads((agent / "settings.json").read_text())
            self.assertIn(str(plugin.resolve()), settings["packages"])
            # The auto-update and any manual rerun call the public installer bare: the layer stays.
            run_script("install.sh", home, "--skip-external", env=env)
            self.assertEqual((agent / "AGENTS.md").read_text(), before)
            self.assertIn("Overlay-only instruction.", before)
            self.assertEqual((home / ".agents/skills/extra-skill").readlink(), overlay.resolve() / "skills/extra-skill")
            self.assertEqual(json.loads((agent / "settings.json").read_text()), settings)
            # --no-overlay drops it, and the next bare run stays without it.
            run_script("install.sh", home, "--skip-external", "--no-overlay", env=env)
            self.assertNotIn("Overlay-only instruction.", (agent / "AGENTS.md").read_text())
            self.assertFalse((home / ".agents/skills/extra-skill").is_symlink())
            self.assertNotIn(str(plugin.resolve()), json.loads((agent / "settings.json").read_text())["packages"])
            run_script("install.sh", home, "--skip-external", env=env)
            self.assertNotIn("Overlay-only instruction.", (agent / "AGENTS.md").read_text())

    def test_a_bare_uninstall_removes_the_recorded_overlay_even_when_its_checkout_is_gone(self):
        for checkout_gone in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                home = base / "home"
                overlay = make_overlay(base)
                plugin = base / "plugin"
                plugin.mkdir()
                (plugin / "package.json").write_text("{}")
                (overlay / "overlay.json").write_text(json.dumps({"plugins": {"gamma": {"name": "gamma", "variable": "PI_GAMMA_ROOT", "path": "../plugin"}}}))
                env = {"WEIHUNG_OVERLAY": "", "PI_GAMMA_ROOT": str(plugin)}
                agent = home / ".pi/agent"
                agent.mkdir(parents=True)
                (agent / "settings.json").write_text(json.dumps({"packages": ["npm:user-package"], "theme": "light"}))
                (agent / "AGENTS.md").write_text("user instructions\n")
                run_script("install.sh", home, "--skip-external", "--force", "--overlay", str(overlay), env=env)
                if checkout_gone:
                    shutil.rmtree(overlay)
                run_script("uninstall.sh", home, "--skip-external", env=env)
                self.assertEqual((agent / "AGENTS.md").read_text(), "user instructions\n")
                self.assertEqual(json.loads((agent / "settings.json").read_text()), {"packages": ["npm:user-package"], "theme": "light"})
                self.assertFalse([path for path in (home / ".agents").rglob("*") if path.is_symlink()])
                self.assertFalse((agent / "rules").exists())

    def test_a_recorded_overlay_that_is_gone_stops_a_bare_install(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            overlay = make_overlay(base)
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            shutil.rmtree(overlay)
            result = run_script("install.sh", home, "--skip-external", env={"WEIHUNG_OVERLAY": ""}, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--no-overlay", result.stderr)
            run_script("install.sh", home, "--skip-external", "--no-overlay", env={"WEIHUNG_OVERLAY": ""})

    def test_a_skill_in_both_checkouts_stops_the_install(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            overlay = make_overlay(base, ("going-to-sleep",))
            result = run_script("install.sh", base / "home", "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""}, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("going-to-sleep exists in both", result.stderr)

    def test_links_into_the_overlay_from_an_earlier_layout_are_repointed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            overlay = make_overlay(base)
            # Before the split, the overlay checkout owned these links and was itself a registered pi package.
            (home / ".pi/agent").mkdir(parents=True)
            (home / ".agents/skills").mkdir(parents=True)
            (home / ".pi/agent/rules").symlink_to(overlay.resolve() / "rules")
            (home / ".pi/agent/agents").symlink_to(overlay.resolve() / "agents")
            (home / ".agents/skills/going-to-sleep").symlink_to(overlay.resolve() / "skills/going-to-sleep")
            (home / ".pi/agent/settings.json").write_text(json.dumps({"packages": [str(overlay.resolve()), "npm:user-package"]}))
            run_script("install.sh", home, "--skip-external", "--overlay", str(overlay), env={"WEIHUNG_OVERLAY": ""})
            self.assertEqual((home / ".pi/agent/rules").readlink(), ROOT / "rules")
            self.assertEqual((home / ".pi/agent/agents").readlink(), ROOT / "agents")
            self.assertEqual((home / ".agents/skills/going-to-sleep").readlink(), ROOT / "skills/going-to-sleep")
            packages = json.loads((home / ".pi/agent/settings.json").read_text())["packages"]
            self.assertNotIn(str(overlay.resolve()), packages)
            self.assertIn("npm:user-package", packages)
            self.assertIn(str(ROOT), packages)


if __name__ == "__main__":
    unittest.main()
