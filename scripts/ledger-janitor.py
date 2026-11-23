#!/usr/bin/env python3
"""Plan or apply conservative cleanup of local worktrees and scratch files."""

import argparse
from datetime import datetime
from itertools import chain
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

DAY = 86400


def run(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=60,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def git(path, *argv):
    return run("git", *argv, cwd=path)


def text(result):
    return os.fsdecode(result.stdout).strip()


def raise_walk_error(error):
    raise error


def files_under(root):
    for directory, dirs, files in os.walk(root, onerror=raise_walk_error):
        for name in [*dirs, *files]:
            yield Path(directory) / name


def folders(root):
    if root.exists() and not root.is_symlink():
        yield from (path for path in sorted(root.iterdir()) if not path.is_symlink() and path.is_dir())


def default_ref(path):
    remote = git(path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if remote.returncode == 0:
        return text(remote)
    if text(git(path, "remote")):
        return None
    refs = [ref for ref in ("refs/heads/main", "refs/heads/master")
            if git(path, "show-ref", "--verify", "--quiet", ref).returncode == 0]
    return refs[0] if len(refs) == 1 else None


def panes():
    try:
        result = run("herdr", "pane", "list")
        return json.loads(result.stdout)["result"]["panes"] if result.returncode == 0 else []
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return []


def inside(path, root):
    return path == root or root in path.parents


def worktree_reason(path, pane_rows, now):
    if not stat.S_ISREG((path / ".git").lstat().st_mode):
        return "not a linked worktree"
    top = git(path, "rev-parse", "--show-toplevel")
    if top.returncode or Path(text(top)).resolve() != path:
        return "cannot verify linked worktree root"
    status = git(path, "status", "--porcelain", "--untracked-files=normal", "--ignored=matching", "--ignore-submodules=none")
    if status.returncode:
        return "git status failed"
    if status.stdout:
        return "dirty or contains ignored files"
    if git(path, "symbolic-ref", "-q", "HEAD").returncode:
        return "detached HEAD"
    branch = default_ref(path)
    if not branch:
        return "default branch unknown"
    merged = git(path, "merge-base", "--is-ancestor", "HEAD", branch)
    if merged.returncode:
        return "unmerged branch" if merged.returncode == 1 else "cannot verify merge"
    if any(inside(Path(pane[key]).resolve(), path) for pane in pane_rows
           if not pane.get("restore_error") for key in ("cwd", "foreground_cwd") if pane.get(key)):
        return "in use by Herdr pane"
    metadata = git(path, "rev-parse", "--absolute-git-dir")
    if metadata.returncode:
        return "cannot verify worktree age"
    git_dir = Path(text(metadata))
    for item in chain((path, git_dir), files_under(git_dir), files_under(path)):
        if item.lstat().st_mtime >= now - 2 * DAY:
            return "touched within 2 days"
    live = run("lsof", "-a", "-d", "cwd", "-Fn", "+D", str(path))
    if live.stdout:
        return "in use by live process"
    if live.returncode != 1 or live.stderr:
        return "cannot verify process CWDs"
    return None


def row(repo, path, reason, owner_hint=None, **extra):
    return dict(repo=repo, path=str(path), reason=reason, owner_hint=owner_hint, **extra)


def worktrees(root, now, apply, actions, left):
    pane_rows = panes()
    seen = set()
    for pane in pane_rows:
        if not (pane.get("restore_error") or "").startswith("Saved directory is unavailable"):
            continue
        path = Path(pane.get("cwd") or "/")
        workspace = pane.get("workspace_id")
        key = (workspace, path)
        if key in seen:
            continue
        seen.add(key)
        repo = path.relative_to(root).parts[0] if inside(path, root) and path != root else None
        left.append(row(repo, path, "Saved directory is unavailable", pane.get("agent"), workspace_id=workspace))
    for repo in folders(root):
        for path in folders(repo):
            owner = None
            try:
                reason = worktree_reason(path, pane_rows, now)
                if (path / ".git").is_file() and not (path / ".git").is_symlink():
                    log = git(path, "log", "-1", "--format=%cn")
                    owner = text(log) or None if log.returncode == 0 else None
                if reason:
                    left.append(row(repo.name, path, reason, owner))
                    continue
                if apply:
                    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
                    if common.returncode:
                        raise ValueError("cannot locate common Git directory")
                    git_dir = f"--git-dir={text(common)}"
                    if run("git", git_dir, "worktree", "remove", str(path), cwd=root).returncode:
                        raise ValueError("git worktree remove refused")
                    actions.append(row(repo.name, path, "removed merged worktree", owner))
                    if run("git", git_dir, "worktree", "prune", cwd=root).returncode:
                        raise ValueError("worktree removed but git worktree prune failed")
                else:
                    actions.append(row(repo.name, path, "would remove merged worktree", owner))
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                left.append(row(repo.name, path, f"worktree check or action failed: {error}", owner))


def references(agent, names, now):
    aliases = {os.fsencode(name): name for name in names}
    aliases.update({json.dumps(name)[1:-1].encode(): name for name in names})
    if not aliases:
        return set()
    # Prefilter lines, then test literals so overlapping names are not lost.
    pattern = re.compile(b"|".join(map(re.escape, sorted(aliases))))
    found = set()
    for root, cutoff in ((agent / "straw-boss/board", 0), (agent / "sessions", now - 7 * DAY)):
        if not root.exists():
            continue
        for path in files_under(root):
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_mtime < cutoff:
                    continue
                with path.open("rb") as source:
                    for line in source:
                        if pattern.search(line):
                            found.update(name for alias, name in aliases.items() if name not in found and alias in line)
                        if len(found) == len(names):
                            return found
            except FileNotFoundError:
                continue  # Session or board file rotated during the scan.
    return found


def scratch_files(projects, agent, now, apply, actions, left):
    candidates = []
    for repo in folders(projects):
        scratch = repo / "scratch"
        if scratch.is_symlink() or not scratch.is_dir():
            continue
        try:
            tracked = git(repo, "ls-files", "-z", "--", "scratch")
            if tracked.returncode or tracked.stdout:
                reason = "cannot check tracked scratch" if tracked.returncode else "tracked scratch"
                left.append(row(repo.name, scratch, reason))
                continue
            for path in sorted(scratch.iterdir()):
                info = path.lstat()
                if stat.S_ISREG(info.st_mode):
                    if info.st_mtime < now - 30 * DAY:
                        candidates.append((repo, path, info))
                    else:
                        left.append(row(repo.name, path, "not older than 30 days"))
        except (OSError, subprocess.TimeoutExpired) as error:
            left.append(row(repo.name, scratch, f"scratch scan failed: {error}"))
    try:
        found = references(agent, {path.name for _, path, _ in candidates}, now)
    except OSError as error:
        for repo, path, _ in candidates:
            left.append(row(repo.name, path, f"reference scan failed: {error}"))
        return
    for repo, path, info in candidates:
        month = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m")
        archive = path.parent / "archive"
        destination = archive / month / path.name
        try:
            if path.name in found:
                left.append(row(repo.name, path, "referenced by board or recent session"))
                continue
            if archive.is_symlink() or destination.parent.is_symlink() or os.path.lexists(destination):
                raise ValueError("archive destination exists or uses a symlink")
            if apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if path.lstat() != info:
                    raise ValueError("source changed during the scan")
                # Unlike rename(), link() cannot overwrite an existing archive file.
                os.link(path, destination, follow_symlinks=False)
                path.unlink()
            reason = "archived old scratch file" if apply else "would archive old scratch file"
            actions.append(row(repo.name, path, reason, destination=str(destination)))
        except (OSError, ValueError) as error:
            left.append(row(repo.name, path, f"archive blocked: {error}"))


def report(result):
    lines = [f"# Ledger janitor ({result['mode']})", ""]
    for key in ("actions", "left"):
        lines.extend([f"## {key.title()} ({len(result[key])})", ""])
        for item in result[key]:
            details = " · ".join(str(item[field]) for field in ("destination", "owner_hint", "workspace_id") if item.get(field))
            lines.append(f"- {item['path']!r}: {item['reason']}" + (f" ({details})" if details else ""))
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show the plan without changing files (default)")
    mode.add_argument("--apply", action="store_true", help="apply the plan and write the daily report")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()
    home = Path.home().resolve()
    agent = home / ".pi/agent"
    now = time.time()
    actions, left = [], []
    worktrees(home / ".herdr/worktrees", now, args.apply, actions, left)
    scratch_files(home / "projects", agent, now, args.apply, actions, left)
    result = dict(mode="apply" if args.apply else "dry-run", actions=actions, left=left)
    summary = report(result)
    if args.apply:
        directory = agent / "ledger-janitor"
        directory.mkdir(parents=True, exist_ok=True)
        day = datetime.fromtimestamp(now).date().isoformat()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as output:
            output.write(summary)
        os.replace(output.name, directory / f"report-{day}.md")
    print(json.dumps(result, ensure_ascii=True) if args.json else summary)


if __name__ == "__main__":
    main()
