"""A local stand-in for the pinned statechart skill source and the TLC jar, selected through PI_STATECHART_PIN."""

import hashlib
import json
import subprocess
from pathlib import Path

SKILL_PATH = "harness/pstack/claude-code/skills/statechart"
SKILL_MD = "---\nname: statechart\ndescription: Test skill\ndisable-model-invocation: true\n---\n# Statechart\n"
ENTRY = "#!/bin/sh\necho \"TLA2TOOLS=$TLA2TOOLS\"\necho \"JAVA=$JAVA\"\necho \"ARGS=$*\"\n"


def make_pin(base: Path, jar: bytes = b"tla2tools fixture\n") -> dict[str, str]:
    """Build the fixture under base and return the environment that makes the installer use it."""
    repo = base / "statechart-source"
    skill = repo / SKILL_PATH
    (skill / "references").mkdir(parents=True)
    (skill / "scripts/backends").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_MD)
    (skill / "references/render.md").write_text("# Render\n")
    (skill / "scripts/statechart.ts").write_text("// entry\n")
    (skill / "scripts/statechart").write_text(ENTRY)
    (skill / "scripts/statechart").chmod(0o755)
    (repo / "README.md").write_text("other plugins\n")
    (repo / "harness/other").mkdir(parents=True)
    (repo / "harness/other/file").write_text("outside the skill\n")
    for command in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
    rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    jar_file = base / "tla2tools.jar"
    jar_file.write_bytes(jar)
    pin = base / "statechart-pin.json"
    pin.write_text(json.dumps({"git": str(repo), "rev": rev, "path": SKILL_PATH, "jar_url": jar_file.as_uri(),
                               "jar_sha256": hashlib.sha256(jar).hexdigest()}))
    return {"PI_STATECHART_PIN": str(pin)}
