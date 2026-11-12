"""The pinned statechart skill: fetched at its revision, run with the pinned TLC jar, removed again by uninstall."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pi_root import external, jsonfile, paths, pins, resources, unattended
from support.statechart import SKILL_PATH, make_pin

LINK = ".agents/skills/statechart"
SKILL_MD_NEXT = "---\nname: statechart\ndescription: Test skill\ndisable-model-invocation: true\n---\n# next revision\n"


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StatechartTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.home.mkdir()
        patch = mock.patch.dict(os.environ, make_pin(self.base))
        patch.start()
        self.addCleanup(patch.stop)

    def install(self, force=False):
        state = jsonfile.read_json(self.home / paths.MARKER)
        resources.install_statechart(self.home, state, force)
        return jsonfile.read_json(self.home / paths.MARKER)

    def run_skill(self, *args, **env):
        return subprocess.run([str(self.home / LINK / "scripts/statechart"), *args], text=True, capture_output=True, check=True,
                              env={**os.environ, **env})

    def test_the_pinned_revision_is_fetched_and_the_skill_dir_is_complete(self):
        self.install()
        skill = self.home / LINK
        self.assertTrue(skill.is_symlink())
        self.assertIn("disable-model-invocation: true", (skill / "SKILL.md").read_text())
        self.assertTrue((skill / "references/render.md").is_file())
        self.assertTrue((skill / "scripts/statechart.ts").is_file())
        clone = self.home / paths.STATECHART_ROOT / "cursor-plugins"
        pin = json.loads(Path(os.environ["PI_STATECHART_PIN"]).read_text())
        head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head, pin["rev"])
        self.assertFalse((clone / "harness/other").exists(), "only the skill's folder is checked out")

    def test_the_command_runs_with_the_pinned_jar_and_keeps_a_java_the_caller_set(self):
        self.install()
        jar = self.home / paths.STATECHART_ROOT / "tla2tools.jar"
        result = self.run_skill("Spec.tla", "--out", "x", JAVA="/fake/java", TLA2TOOLS="")
        self.assertIn(f"TLA2TOOLS={jar}", result.stdout)
        self.assertIn("JAVA=/fake/java", result.stdout)
        self.assertIn("ARGS=Spec.tla --out x", result.stdout)

    def fake_java(self, version_line):
        java = self.base / "bin/java"
        java.parent.mkdir(exist_ok=True)
        java.write_text(f"#!/bin/sh\necho '{version_line}' >&2\n")
        java.chmod(0o755)
        return java

    def test_a_java_11_or_later_on_the_path_is_found(self):
        self.install()
        java = self.fake_java('openjdk version "21.0.4" 2024-07-16')
        env = {key: value for key, value in os.environ.items() if key not in ("JAVA", "JAVA_HOME")}
        result = subprocess.run([str(self.home / LINK / "scripts/statechart")], text=True, capture_output=True, check=True,
                                env={**env, "PATH": f"{java.parent}{os.pathsep}{os.environ['PATH']}"})
        self.assertIn(f"JAVA={java}", result.stdout)

    def test_a_java_before_11_is_not_used(self):
        self.install()
        java = self.fake_java('java version "1.8.0_402"')
        env = {key: value for key, value in os.environ.items() if key not in ("JAVA", "JAVA_HOME")}
        result = subprocess.run([str(self.home / LINK / "scripts/statechart")], text=True, capture_output=True, check=False,
                                env={**env, "PATH": f"{java.parent}{os.pathsep}{os.environ['PATH']}"})
        # Another Java 11+ on this machine may answer instead; the old one never does.
        self.assertNotIn(f"JAVA={java}", result.stdout)
        if result.returncode:
            self.assertEqual(result.returncode, 127)
            self.assertIn("needs Java 11 or later", result.stderr)

    def test_a_home_path_with_shell_metacharacters_reaches_the_wrapper_verbatim_and_runs_nothing(self):
        odd = self.base / "h'o\"m$X`touch pwned`}e"
        odd.mkdir()
        self.home = odd
        self.install()
        wrapper = (odd / LINK / "scripts/statechart").read_text()
        self.assertNotIn(str(odd), wrapper.replace(shlex.quote(str(odd)), ""))
        result = self.run_skill(JAVA="/fake/java", TLA2TOOLS="")
        self.assertIn(f"TLA2TOOLS={odd / paths.STATECHART_ROOT / 'tla2tools.jar'}", result.stdout)
        self.assertFalse(Path("pwned").exists() or (odd / "pwned").exists())

    def test_the_java_version_is_read_from_the_line_that_has_it(self):
        self.install()
        java = self.fake_java('Picked up JAVA_TOOL_OPTIONS: -Xmx1g\nopenjdk version "21.0.4" 2024-07-16')
        env = {key: value for key, value in os.environ.items() if key not in ("JAVA", "JAVA_HOME")}
        result = subprocess.run([str(self.home / LINK / "scripts/statechart")], text=True, capture_output=True, check=True,
                                env={**env, "PATH": f"{java.parent}{os.pathsep}{os.environ['PATH']}"})
        self.assertIn(f"JAVA={java}", result.stdout)

    def test_a_reinstall_restores_deleted_and_edited_clone_files(self):
        self.install()
        source = self.home / paths.STATECHART_ROOT / "cursor-plugins" / SKILL_PATH
        (source / "references/render.md").write_text("edited\n")
        (source / "scripts/statechart.ts").unlink()
        (source / "stray").write_text("untracked\n")
        self.install()
        self.assertEqual((source / "references/render.md").read_text(), "# Render\n")
        self.assertTrue((source / "scripts/statechart.ts").is_file())
        self.assertFalse((source / "stray").exists())

    def test_a_failed_jar_on_a_pin_bump_keeps_the_previous_revision_and_jar_live(self):
        self.install()
        pin = Path(os.environ["PI_STATECHART_PIN"])
        old = json.loads(pin.read_text())
        repo = Path(old["git"])
        (repo / SKILL_PATH / "SKILL.md").write_text(SKILL_MD_NEXT)
        for command in (["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "next"]):
            subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
        rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        pin.write_text(json.dumps({**old, "rev": rev, "jar_sha256": hashlib.sha256(b"other").hexdigest()}))
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.install()
        self.assertNotIn("next revision", (self.home / LINK / "SKILL.md").read_text())
        self.assertEqual(sha256_of(self.home / paths.STATECHART_ROOT / "tla2tools.jar"), old["jar_sha256"])

    def test_a_skill_dir_that_is_a_symlink_is_unlinked_not_followed(self):
        precious = self.base / "precious"
        precious.mkdir()
        (precious / "keep").write_text("mine\n")
        root = self.home / paths.STATECHART_ROOT
        root.mkdir(parents=True)
        (root / "skill").symlink_to(precious)
        self.install()
        self.assertEqual((precious / "keep").read_text(), "mine\n")
        self.assertFalse((root / "skill").is_symlink())
        self.assertTrue((self.home / LINK / "SKILL.md").is_file())

    def test_a_broken_clone_inside_a_repository_never_touches_that_repository(self):
        notes = self.home / "notes.txt"
        notes.write_text("committed\n")
        for command in (["init", "-q"], ["add", "notes.txt"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "home"]):
            subprocess.run(["git", "-C", str(self.home), *command], check=True, capture_output=True)
        notes.write_text("uncommitted work\n")
        (self.home / paths.STATECHART_ROOT / "cursor-plugins/.git").mkdir(parents=True)
        self.install()
        self.assertEqual(notes.read_text(), "uncommitted work\n")
        remote = subprocess.run(["git", "-C", str(self.home), "config", "--get", "remote.origin.url"], capture_output=True, text=True)
        self.assertEqual(remote.stdout, "")
        self.assertTrue((self.home / LINK / "SKILL.md").is_file())

    def test_git_variables_in_the_environment_never_redirect_the_clone(self):
        other = self.base / "other"
        other.mkdir()
        (other / "notes.txt").write_text("committed\n")
        for command in (["init", "-q"], ["add", "notes.txt"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "other"]):
            subprocess.run(["git", "-C", str(other), *command], check=True, capture_output=True)
        (other / "notes.txt").write_text("uncommitted work\n")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}):
            self.install()
        self.assertEqual((other / "notes.txt").read_text(), "uncommitted work\n")
        self.assertTrue((self.home / LINK / "SKILL.md").is_file())

    def test_a_restore_that_git_refuses_stops_the_install(self):
        self.install()
        clone = self.home / paths.STATECHART_ROOT / "cursor-plugins"
        (clone / SKILL_PATH / "references/render.md").write_text("edited\n")
        (clone / ".git/index.lock").write_text("")
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()

    def test_a_skill_path_that_is_a_file_is_replaced(self):
        root = self.home / paths.STATECHART_ROOT
        root.mkdir(parents=True)
        (root / "skill").write_text("stray\n")
        self.install()
        self.assertTrue((self.home / LINK / "SKILL.md").is_file())

    def test_a_failed_source_on_a_pin_bump_keeps_the_previous_jar_live(self):
        self.install()
        pin = Path(os.environ["PI_STATECHART_PIN"])
        old = json.loads(pin.read_text())
        jar = self.base / "tla2tools-next.jar"
        jar.write_bytes(b"next jar\n")
        pin.write_text(json.dumps({**old, "rev": "0" * 40, "jar_url": jar.as_uri(), "jar_sha256": sha256_of(jar)}))
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()
        self.assertEqual(sha256_of(self.home / paths.STATECHART_ROOT / "tla2tools.jar"), old["jar_sha256"])

    def test_a_second_install_changes_nothing_and_fetches_nothing(self):
        first = self.install()
        calls = []
        with mock.patch.object(external, "run", lambda args, _home: calls.append(args)):
            second = self.install()
        self.assertEqual([args for args in calls if "fetch" in args or "curl" in args or "init" in args], [])
        self.assertEqual(first, second)
        self.assertTrue((self.home / LINK / "SKILL.md").is_file())

    def test_a_jar_that_does_not_match_its_checksum_stops_the_install_and_is_not_kept(self):
        pin = Path(os.environ["PI_STATECHART_PIN"])
        data = json.loads(pin.read_text())
        data["jar_sha256"] = hashlib.sha256(b"other").hexdigest()
        pin.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.install()
        root = self.home / paths.STATECHART_ROOT
        self.assertEqual(list(root.glob("*.jar*")), [])
        self.assertFalse((self.home / LINK).exists() or (self.home / LINK).is_symlink())

    def test_a_conflicting_skill_fails_without_force_and_is_restored_after_uninstall(self):
        link = self.home / LINK
        link.parent.mkdir(parents=True)
        link.mkdir()
        (link / "mine").write_text("user copy\n")
        with self.assertRaisesRegex(ValueError, "use --force"):
            self.install()
        self.assertEqual((link / "mine").read_text(), "user copy\n")
        self.install(force=True)
        self.assertTrue((link / "SKILL.md").is_file())
        resources.uninstall_ported_resources(self.home, jsonfile.read_json(self.home / paths.MARKER))
        self.assertEqual((link / "mine").read_text(), "user copy\n")
        self.assertFalse((self.home / paths.STATECHART_ROOT).exists())

    def test_uninstall_removes_everything_install_added(self):
        state = self.install()
        self.assertIn(LINK, state["ported_resources"])
        resources.uninstall_ported_resources(self.home, state)
        self.assertFalse((self.home / LINK).exists() or (self.home / LINK).is_symlink())
        self.assertFalse((self.home / paths.STATECHART_ROOT).exists())

    def test_the_unattended_profile_leaves_the_skill_out_and_takes_it_back(self):
        self.assertIn("statechart", pins.UNATTENDED_DROPPED_SKILLS)
        self.assertIn("statechart", unattended.dropped_skills(unattended.UNATTENDED))
        state = self.install()
        resources.uninstall_statechart(self.home, state)
        self.assertFalse((self.home / LINK).is_symlink())
        self.assertFalse((self.home / paths.STATECHART_ROOT).exists())
        self.assertNotIn(LINK, jsonfile.read_json(self.home / paths.MARKER).get("ported_resources", {}))
        self.assertNotIn("statechart_root", jsonfile.read_json(self.home / paths.MARKER))

    def test_the_shipped_pin_names_a_full_revision_and_a_checksummed_jar(self):
        self.assertRegex(pins.STATECHART["rev"], r"^[0-9a-f]{40}$")
        self.assertRegex(pins.STATECHART["jar_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(pins.STATECHART["path"], SKILL_PATH)
        self.assertTrue(pins.STATECHART["jar_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
