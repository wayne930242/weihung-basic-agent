"""Commands run outside this process: npm, pi, herdr, git."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


# Variables that make git act on a repository other than the one each command names with `-C`.
GIT_REPOSITORY_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE")


def environment(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in GIT_REPOSITORY_VARIABLES}
    env["HOME"] = str(home)
    env["PI_CODING_AGENT_DIR"] = str(home / ".pi/agent")
    return env


def require(tool: str, hint: str) -> None:
    """Stop with a clear message when a tool the install needs is not on PATH."""
    if shutil.which(tool) is None:
        raise ValueError(f"{tool} is not on PATH; {hint}")


def run(args: list[str], home: Path) -> None:
    subprocess.run(args, check=True, env=environment(home))


def capture(args: list[str], home: Path) -> str:
    """The stdout of a command that reports state; a failed call reports nothing."""
    result = subprocess.run(args, capture_output=True, text=True, check=False, env=environment(home))
    return result.stdout


def run_optional_plugin(action: str, home: Path, source: str) -> None:
    # An optional plugin must not stop the install or uninstall: a failed `pi` call leaves its settings entry to the write that follows.
    try:
        run(["pi", action, source], home)
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"could not run pi {action} for {source}: {error}; continuing.", file=sys.stderr)
