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
    def test_plan_and_apply(self):
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

            def git(*args, cwd=repo):
                return subprocess.check_output(["git", *args], cwd=cwd, env=env, text=True)

            def run(*args):
                return json.loads(subprocess.check_output(
                    [sys.executable, str(SCRIPT), "--json", *args], env=env, text=True, cwd=home))

            git("init", "-b", "main")
            git("config", "user.name", "Fixture Owner")
            git("config", "user.email", "fixture@example.test")
            git("commit", "--allow-empty", "-m", "base")
            root = home / ".herdr/worktrees/example"
            for name in ("merged", "dirty", "unmerged", "busy"):
                git("worktree", "add", "-b", name, str(root / name))
            (root / "dirty/notes").touch()
            git("commit", "--allow-empty", "-m", "not merged", cwd=root / "unmerged")
            scratch = repo / "scratch"
            scratch.mkdir()
            paths = [scratch / name for name in ("old.md", "board.md", "recent.md")]
            for path in paths:
                path.touch()
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
            with subprocess.Popen(["/bin/sleep", "30"], cwd=root / "busy") as busy:
                try:
                    plan = run()
                    self.assertTrue((root / "merged").exists())
                    self.assertTrue(paths[0].exists())
                    self.assertFalse(list(home.glob(".pi/agent/ledger-janitor/*.md")))
                    applied = run("--apply")
                finally:
                    busy.terminate()
            for result in (plan, applied):
                self.assertEqual({Path(row["path"]).name for row in result["actions"]}, {"merged", "old.md"})
                left = {Path(row["path"]).name: row for row in result["left"]}
                for name, reason in (("dirty", "dirty"), ("busy", "in use"), ("unmerged", "unmerged"),
                                     ("board.md", "referenced"), ("recent.md", "referenced"), ("scratch", "tracked")):
                    self.assertIn(reason, left[name]["reason"])
                self.assertEqual(left["unmerged"]["owner_hint"], "Fixture Owner")
                self.assertEqual(left["dead"]["workspace_id"], "w123")
                self.assertEqual(left["dead"]["reason"], "Saved directory is unavailable")
            self.assertFalse((root / "merged").exists())
            self.assertEqual(git("branch", "--list", "merged").strip(), "merged")
            self.assertEqual(len(list(scratch.glob("archive/*/old.md"))), 1)
            self.assertTrue(paths[1].exists() and paths[2].exists() and tracked_file.exists())
            self.assertEqual(len(list(home.glob(".pi/agent/ledger-janitor/report-*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
