"""Exercise the janitor against real Git repositories in an isolated HOME."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ledger-janitor.py"


@unittest.skipUnless(shutil.which("lsof"), "requires lsof")
class JanitorTests(unittest.TestCase):
    def test_plan_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            env = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1"}
            fake_bin = home / "bin"
            fake_bin.mkdir()
            dead = home / ".herdr/worktrees/example/dead"
            herdr = fake_bin / "herdr"
            panes = {"result": {"panes": [{"cwd": str(dead), "workspace_id": "w123",
                                           "restore_error": "Saved directory is unavailable. Restore the directory."}]}}
            herdr.write_text(f"#!{sys.executable}\nprint({json.dumps(panes)!r})\n")
            herdr.chmod(0o755)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            repo = home / "projects/example"
            repo.mkdir(parents=True)

            def git(*args: str, cwd: Path = repo) -> str:
                return subprocess.check_output(["git", *args], cwd=cwd, env=env, text=True)

            def run(*args: str) -> dict:
                return json.loads(subprocess.check_output(
                    [sys.executable, str(SCRIPT), "--json", *args], env=env, text=True, cwd=home))

            git("init", "-b", "main")
            git("config", "user.name", "Fixture Owner")
            git("config", "user.email", "fixture@example.test")
            git("commit", "--allow-empty", "-m", "base")
            root = home / ".herdr/worktrees/example"
            for name in ("merged", "dirty", "unmerged", "busy", "ignored", "group/nested", "collision"):
                git("worktree", "add", "-b", name, str(root / name))
            (root / "main").mkdir()
            git("init", "-b", "main", cwd=root / "main")
            (root / "empty").mkdir()
            (repo / ".git/info/exclude").write_text("node_modules/\n/scratch/\n/.pi/memory/\n")
            for note in ("scratch/nested/decision.md", ".pi/memory/context.md"):
                path = root / "ignored" / note
                path.parent.mkdir(parents=True)
                path.write_text(note)
            blocked_note = root / "collision/scratch/decision.md"
            blocked_note.parent.mkdir()
            blocked_note.write_text("keep original")
            (root / "ignored/node_modules").mkdir()
            (root / "ignored/node_modules/output").touch()
            (root / "dirty/notes").touch()
            git("commit", "--allow-empty", "-m", "not merged", cwd=root / "unmerged")
            scratch = repo / "scratch"
            scratch.mkdir()
            paths = [scratch / name for name in ("old.md", "board.md", "recent.md")]
            for path in paths:
                path.touch()
            (scratch / "young.md").touch()
            board = home / ".pi/agent/straw-boss/board"
            board.mkdir(parents=True)
            (board / "todo.json").write_bytes(b" " * (1024 * 1024 - 4) + b"board.md")
            sessions = home / ".pi/agent/sessions"
            sessions.mkdir()
            (sessions / "session.jsonl").write_text("recent.md")
            tracked = home / "projects/tracked"
            (tracked / "scratch").mkdir(parents=True)
            tracked_file = tracked / "scratch/tracked.md"
            tracked_file.touch()
            git("init", "-b", "main", cwd=tracked)
            git("add", "scratch", cwd=tracked)
            old = time.time() - 40 * 86400
            for path in [*root.rglob("*"), *paths, tracked_file, *(repo / ".git/worktrees").rglob("*")]:
                os.utime(path, (old, old))
            month = time.strftime("%Y-%m", time.localtime(old))
            destination = scratch / f"archive/{month}/example/collision/scratch/decision.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("keep archive")
            with subprocess.Popen(["/bin/sleep", "30"], cwd=root / "busy") as busy:
                try:
                    plan = run()
                    self.assertTrue((root / "merged").exists())
                    self.assertTrue(paths[0].exists())
                    self.assertFalse(list(home.glob(".pi/agent/ledger-janitor/*.md")))
                    healthy_herdr = herdr.read_text()
                    herdr.write_text(f"#!{sys.executable}\nraise SystemExit(1)\n")
                    unavailable = run()
                    herdr.write_text(healthy_herdr)
                    applied = run("--apply")
                finally:
                    busy.terminate()
            for result in (plan, applied):
                actions = {Path(row["path"]).name for row in result["actions"]}
                left = {Path(row["path"]).name: row for row in result["left"]}
                with self.subTest(check="ignored files"):
                    self.assertIn("ignored", actions)
                with self.subTest(check="namespace directories and primary checkout"):
                    self.assertIn("nested", actions)
                    self.assertFalse({"main", "group", "empty"} & left.keys())
                with self.subTest(check="waiting counts"):
                    self.assertEqual(result.get("waiting"), {"not older than 30 days": 1,
                                                            "referenced by board or recent session": 2,
                                                            "in use by live process": 1})
                self.assertEqual(actions, {"merged", "ignored", "nested", "old.md"})
                self.assertEqual(set(left), {"dirty", "unmerged", "scratch", "dead", "collision"})
                self.assertIn("archive destination exists", left["collision"]["reason"])
                for name, reason in (("dirty", "dirty"), ("unmerged", "unmerged"), ("scratch", "tracked")):
                    self.assertIn(reason, left[name]["reason"])
                self.assertEqual(left["unmerged"]["owner_hint"], "Fixture Owner")
                self.assertEqual(left["dead"]["workspace_id"], "w123")
                self.assertEqual(left["dead"]["reason"], "Saved directory is unavailable")
            with self.subTest(check="archive before removal"):
                for note in ("scratch/nested/decision.md", ".pi/memory/context.md"):
                    copies = list(scratch.glob(f"archive/*/example/ignored/{note}"))
                    self.assertEqual(len(copies), 1)
                    self.assertEqual(copies[0].read_text(), note)
            with self.subTest(check="Herdr failure"):
                self.assertEqual({Path(row["path"]).name for row in unavailable["actions"]}, {"old.md"})
                self.assertEqual(sum("cannot read Herdr panes" in row["reason"] for row in unavailable["left"]), 7)
            self.assertEqual(blocked_note.read_text(), "keep original")
            self.assertEqual(destination.read_text(), "keep archive")
            self.assertFalse((root / "merged").exists())
            self.assertEqual(git("branch", "--list", "merged").strip(), "merged")
            self.assertEqual(len(list(scratch.glob("archive/*/old.md"))), 1)
            self.assertTrue(paths[1].exists() and paths[2].exists() and tracked_file.exists())
            self.assertEqual(len(list(home.glob(".pi/agent/ledger-janitor/report-*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
