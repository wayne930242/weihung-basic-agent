#!/usr/bin/env python3
"""List and bump the exact versions pinned in scripts/pi_root/pins.py, and keep them current on a schedule."""

import argparse
import atexit
import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "scripts/pi_root/pins.py"
# Files that quote a pin verbatim and must move with it.
QUOTING_FILES = (TARGET, ROOT / "docs/reference.md", *sorted((ROOT / "tests").glob("*.py")),
                 *sorted((ROOT / "tests").glob("*.sh")), *sorted((ROOT / "tests").glob("*.mjs")))
NPM_PIN = re.compile(r"^(npm:(?:@[^/@]+/)?[^/@]+)@(.+)$")
GIT_PIN = re.compile(r"^(git:[^@]+)@([0-9a-f]{7,40})$")
PLAIN_NPM_PIN = re.compile(r"^([^/@:]+)@(.+)$")
# Herdr plugins are installed from a folder of a GitHub repository at a release tag.
GITHUB = "https://github.com"
RELEASE_TAG = re.compile(r"^v\d+\.\d+\.\d+$")
MAIN_BRANCH = "main"
# npm pins `auto` leaves alone: a pi-herdr-agents bump means checking the role discovery pi-straw-boss's role pack registers on.
# pi-straw-boss stays auto although it ships the roles (its role pack, since 0.79.0): its release flow runs `/boss roles-check`
# (the boss's decision, 2026-11-13).
MANUAL_PINS = {"pi-herdr-agents"}
# Installing a new pi-straw-boss restarts the sb server (every session auto-upgrades), which drops a live train's in-memory
# records (2026-11-21 07:42Z): `auto` holds it, without rejecting it, while `train status` shows a live train or cannot be read,
# checked before the run and again right before the install (the boss's decision, 2026-11-21).
SB_PIN = "pi-straw-boss"
SB_CLI = Path.home() / ".pi/agent/npm/node_modules/pi-straw-boss/dist/server/cli.mjs"
# Fork pins follow an integration or PR branch instead of the remote HEAD, so `outdated` and a named `bump` never move
# them to the default branch. `forks` checks each against its upstream; once upstream releases what a fork carries, the pin
# returns to the npm release (pi-herdr-agents then stays out of `auto` through MANUAL_PINS).
class Fork(NamedTuple):
    branch: str  # the fork branch the pin follows
    upstream: str  # <owner>/<repo> the fork tracks
    prs: tuple[int, ...]  # upstream PRs the fork carries until upstream releases them (docs/reference.md names each)
    kept: tuple[int, ...] = ()  # PRs upstream closed unmerged that the fork keeps carrying on purpose
    pinned_by: str | None = None  # a fork pin whose package.json pins this fork as a git dependency, instead of pins.py
    track_tag: bool = False  # compare with upstream's newest release tag (a dependency consumed by release), not its default branch


FORKS = {
    # #123 (reviewer/judge one-shots on the isolated path) closed as superseded by #262: on upstream 0.13.0 such a call
    # gets a fresh tool-less query and no error (rerun 2026-11-20). The fork still carries its tested route, re-keyed on
    # pi's system messages, until the next fork rebase drops it; nothing breaks without it.
    "github.com/wayne930242/pi-claude-bridge": Fork("weihung-integration", "elidickinson/pi-claude-bridge", (123, 131, 133, 225, 226), kept=(123,)),
    "github.com/wayne930242/pi-herdr-agents": Fork("weihung/v3-integration", "giuseppecrj/pi-herdr-agents", (87,), kept=(87,)),
    # The pi-herdr-agents engine since upstream moved it into @nubl/maestro; the herdr fork's package.json pins this fork.
    "github.com/wayne930242/maestro": Fork("weihung-integration", "nublai/maestro", (14, 15, 16, 17, 18),
                                          pinned_by="github.com/wayne930242/pi-herdr-agents", track_tag=True),
}
FORK_BRANCHES = {name: fork.branch for name, fork in FORKS.items() if not fork.pinned_by}
STATE_DIR = Path.home() / ".local/state/weihung-agent-root"
STATE_FILE = STATE_DIR / "pi-autoupdate.json"
LOG_FILE = STATE_DIR / "pi-autoupdate.log"
LAUNCHD_LABEL = "com.weihung.agent-root.pi-autoupdate"
LAUNCHD_PLIST = Path.home() / "Library/LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
SCHEDULE = {"Hour": 6, "Minute": 0}
SMOKE_TIMEOUT_SECONDS = 120
# Tools install.sh calls; launchd starts jobs with a bare PATH, so the schedule records where each lives.
# python3 comes first so its directory precedes /usr/bin, whose Python is too old for pi-target.py.
REQUIRED_TOOLS = ("python3", "pi", "npm", "node", "git", "bash")
OPTIONAL_TOOLS = ("herdr", "playwriter")
SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


class Pin(NamedTuple):
    kind: str  # "npm", "git", or "herdr" (a Herdr plugin: <owner>/<repo>/<folder> at a release tag)
    prefix: str  # the source without its version, exactly as the source files quote it
    current: str

    @property
    def name(self) -> str:
        return self.prefix.removeprefix("npm:").removeprefix("git:")

    def quoted(self, version: str) -> str:
        """The pin at `version` as the source files spell it."""
        return f'"{self.prefix}", "{version}"' if self.kind == "herdr" else f"{self.prefix}@{version}"


class FreshSourceLoader(SourceFileLoader):
    """Compile from source on every load: a cached .pyc is keyed on mtime in whole seconds and size, so a
    pin rewritten to an equally long version within the same second would still load as the old one."""

    def get_code(self, fullname: str):
        return self.source_to_code(self.get_data(self.path), self.path)


def load_target():
    spec = importlib.util.spec_from_file_location("pi_root_pins", TARGET, loader=FreshSourceLoader("pi_root_pins", str(TARGET)))
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_pins() -> list[Pin]:
    target = load_target()
    pins = []
    for value in [*target.PACKAGES, target.ANCHORLOOP_PACKAGE]:
        source = value["source"] if isinstance(value, dict) else value
        if match := NPM_PIN.match(source):
            pins.append(Pin("npm", match[1], match[2]))
        elif match := GIT_PIN.match(source):
            pins.append(Pin("git", match[1], match[2]))
    for plain in (target.PLAYWRITER, target.AGENT_DESKTOP, target.TEAM_TOON_TACK):
        if match := PLAIN_NPM_PIN.match(plain):
            pins.append(Pin("npm", match[1], match[2]))
    for _, repository_path, ref, _ in target.HERDR_PLUGINS:
        pins.append(Pin("herdr", repository_path, ref))
    return pins


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


_clones: dict[str, Path] = {}
_clone_lock = threading.Lock()


def plugin_remote(repository: str) -> str:
    return f"{GITHUB}/{repository}"


def plugin_clone(repository: str) -> Path:
    """A blobless bare clone of a plugin's repository (commits, trees and tags, no file contents), made once per run."""
    with _clone_lock:
        if repository not in _clones:
            directory = Path(tempfile.mkdtemp(prefix="pi-pins-plugin-"))
            atexit.register(shutil.rmtree, directory, True)
            run(["git", "clone", "--quiet", "--bare", "--filter=blob:none", plugin_remote(repository), str(directory)])
            _clones[repository] = directory
        return _clones[repository]


def latest_plugin_tag(pin: Pin) -> str:
    """The newest release tag when the plugin's folder differs there from the pinned tag, else the pinned tag:
    the repository tags far more often than the plugin changes, and each new tag reinstalls the plugin."""
    owner, repository, folder = pin.prefix.split("/", 2)
    clone = str(plugin_clone(f"{owner}/{repository}"))
    tags = [tag for tag in run(["git", "-C", clone, "tag", "--sort=-v:refname"]).splitlines() if RELEASE_TAG.match(tag)]
    if not tags:
        raise ValueError(f"{owner}/{repository} has no release tag")

    def tree(tag: str) -> str:
        return run(["git", "-C", clone, "rev-parse", f"{tag}:{folder}"])

    return pin.current if tree(tags[0]) == tree(pin.current) else tags[0]


def latest(pin: Pin) -> str:
    if pin.kind == "npm":
        return run(["npm", "view", pin.name, "version"])
    if pin.kind == "herdr":
        return latest_plugin_tag(pin)
    ref = f"refs/heads/{FORK_BRANCHES[pin.name]}" if pin.name in FORK_BRANCHES else "HEAD"
    heads = run(["git", "ls-remote", f"https://{pin.name}", ref])
    if not heads:
        raise ValueError(f"{pin.name} has no {ref}")
    return heads.split()[0]


def latest_all(pins: list[Pin]) -> list[str]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(latest, pins))


def short(pin: Pin, version: str) -> str:
    return version[:7] if pin.kind == "git" else version


def outdated() -> None:
    pins = collect_pins()
    width = max(len(pin.name) for pin in pins)
    behind = 0
    for pin, newest in zip(pins, latest_all(pins), strict=True):
        status = "ok" if newest == pin.current else "differs"
        behind += status != "ok"
        suffix = {"git": f" (git: {FORK_BRANCHES.get(pin.name, 'remote HEAD')})", "herdr": " (herdr plugin)"}.get(pin.kind, "")
        print(f"{pin.name:<{width}}  {short(pin, pin.current):<9} {short(pin, newest):<9} {status}{suffix}")
    print(f"\n{behind} of {len(pins)} pins differ from the registry.")


def gh_api(path: str, jq: str) -> str:
    return run(["gh", "api", path, "--jq", jq])


def fork_pin(name: str, fork: Fork) -> str:
    """The commit the fork is pinned to: in pins.py, or in the package.json of the fork pin that depends on it."""
    if fork.pinned_by:
        parent = fork.pinned_by.removeprefix("github.com/")
        manifest = gh_api(f"repos/{parent}/contents/package.json?ref={fork_pin(fork.pinned_by, FORKS[fork.pinned_by])}",
                          ".content | @base64d")
        match = re.search(rf"{re.escape(name.removeprefix('github.com/'))}(?:\.git)?#([0-9a-f]{{7,40}})", manifest)
        if not match:
            raise ValueError(f"{fork.pinned_by}'s package.json does not pin {name}")
        return match[1]
    match = re.search(rf"git:{re.escape(name)}@([0-9a-f]{{7,40}})", TARGET.read_text())
    if not match:
        raise ValueError(f"{name} has no git pin in {TARGET}")
    return match[1]


def newest_tag(repository: str) -> str | None:
    tags = [tag for tag in gh_api(f"repos/{repository}/tags?per_page=100", ".[].name").splitlines() if RELEASE_TAG.match(tag)]
    return max(tags, key=lambda tag: tuple(int(part) for part in tag[1:].split(".")), default=None)


def contains(repository: str, ref: str, commit: str) -> bool:
    return gh_api(f"repos/{repository}/compare/{ref}...{commit}", ".status") in ("behind", "identical")


def pr_state(repository: str, number: int, tag: str | None) -> str:
    state, merge_commit = gh_api(f"repos/{repository}/pulls/{number}",
                                 '(if .merged_at then "merged" else .state end) + " " + (.merge_commit_sha // "-")').split()
    if state == "merged":
        return f"released in {tag}" if tag and contains(repository, tag, merge_commit) else "merged, unreleased"
    return state


def fork_report(name: str, fork: Fork) -> tuple[list[str], list[str]]:
    """Lines describing one fork against its upstream, and the actions they call for."""
    fork_repository = name.removeprefix("github.com/")
    tag = newest_tag(fork.upstream)
    if fork.track_tag and not tag:
        raise ValueError(f"{fork.upstream} has no release tag to track")
    base = tag if fork.track_tag else gh_api(f"repos/{fork.upstream}", ".default_branch")
    owner = fork.upstream.split("/")[0]
    branch = fork.branch.replace("/", "%2F")
    ahead, behind = gh_api(f"repos/{fork_repository}/compare/{owner}:{base}...{branch}",
                           '"\\(.ahead_by) \\(.behind_by)"').split()
    head = gh_api(f"repos/{fork_repository}/branches/{branch}", ".commit.sha")
    pinned = fork_pin(name, fork)
    states = {number: pr_state(fork.upstream, number, tag) for number in fork.prs}
    lines = [f"{fork_repository} ({fork.branch}) vs {fork.upstream}:{base}, newest tag {tag or 'none'}"
             + (f", pinned by {fork.pinned_by.removeprefix('github.com/')}" if fork.pinned_by else ""),
             f"  pin {pinned[:7]}, branch head {head[:7]}; {ahead} ahead, {behind} behind upstream"]
    lines += [f"  #{number}: {state}{' (kept on purpose)' if number in fork.kept else ''}" for number, state in states.items()]
    actions = []
    if not head.startswith(pinned):
        actions.append(f"pin lags the fork branch: update {fork.pinned_by}'s package.json, then bump it" if fork.pinned_by
                       else f"pin lags the fork branch: `bump {name}`")
    if behind != "0":
        actions.append(f"{behind} upstream commits missing: merge (or rebase, which needs a force push)")
    closed = [f"#{number}" for number, state in states.items() if state == "closed" and number not in fork.kept]
    if closed:
        actions.append(f"closed without merging: {', '.join(closed)}; drop it, or keep carrying it (add to `kept`)")
    if fork.prs and not fork.kept and all(state.startswith("released") for state in states.values()):
        actions.append("upstream released every carried PR: return to the npm release (see pins.py)")
    return lines, actions


def forks() -> int:
    """Report every fork's drift from upstream and the state of the PRs it carries; 1 when any needs action."""
    with ThreadPoolExecutor(max_workers=len(FORKS)) as pool:
        reports = list(pool.map(lambda item: fork_report(*item), FORKS.items()))
    pending = 0
    for lines, actions in reports:
        print("\n".join(lines))
        print("\n".join(f"  -> {action}" for action in actions) if actions else "  ok")
        pending += bool(actions)
    print(f"\n{pending} of {len(FORKS)} forks need action.")
    return 1 if pending else 0


def select(pins: list[Pin], names: list[str]) -> list[Pin]:
    if not names:
        return [pin for pin in pins if pin.kind != "git"]
    known = {pin.name: pin for pin in pins}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError(f"not a pinned package: {', '.join(unknown)}; run `outdated` for the names")
    return [known[name] for name in names]


def rewrite(old: str, new: str) -> list[Path]:
    touched = []
    for path in QUOTING_FILES:
        text = path.read_text()
        if old in text:
            path.write_text(text.replace(old, new))
            touched.append(path)
    return touched


def bump(names: list[str]) -> None:
    chosen = select(collect_pins(), names)
    bumped = []
    for pin, newest in zip(chosen, latest_all(chosen), strict=True):
        if newest == pin.current:
            continue
        touched = rewrite(pin.quoted(pin.current), pin.quoted(newest))
        if not touched:
            raise ValueError(f"{pin.quoted(pin.current)} is not quoted in any pinned file")
        bumped.append(pin.name)
        print(f"{pin.name}: {short(pin, pin.current)} -> {short(pin, newest)} ({', '.join(p.name for p in touched)})")
    if not bumped:
        print("Nothing to bump.")
        return
    if any(name.endswith("pi-herdr-agents") for name in bumped):
        print("pi-herdr-agents changed: check that pi-straw-boss's role pack still registers (subagents_list, /boss roles-check) "
              "and update the pins quoted in docs/reference.md.")
    if not names:
        print("Git pins were left alone; name them explicitly to bump them.")
    print("Review `git diff`, run the tests, then `bash scripts/install.sh` and reload pi.")


class StepFailed(ValueError):
    """A verification or install step rejected an update."""


class RestoreFailed(RuntimeError):
    """Reinstalling the previous pins failed, so the machine no longer matches the repository."""


def git(*args: str) -> str:
    return run(["git", "-C", str(ROOT), *args])


def test_commands() -> list[list[str]]:
    tests = ROOT / "tests"
    return [
        *(["bash", str(path)] for path in sorted(tests.glob("*.sh"))),
        *([sys.executable, str(path)] for path in sorted(tests.glob("*.py"))),
        *(["node", "--experimental-strip-types", "--test", str(path)] for path in sorted(tests.glob("*.mjs"))),
    ]


def step(name: str, command: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd or ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])
        raise StepFailed(f"{name} failed: {' '.join(command[-2:])}\n{tail}")


def failing_tests() -> set[str]:
    failing = set()
    for command in test_commands():
        try:
            step("tests", command)
        except StepFailed:
            failing.add(command[-1])
    return failing


def smoke() -> None:
    """Start pi against the installed configuration; a package that fails to load makes pi exit non-zero."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    request = json.dumps({"id": "smoke", "type": "get_commands"}) + "\n"
    try:
        result = subprocess.run(["pi", "--mode", "rpc", "--no-session", "--offline", "--no-approve"], input=request,
                                cwd=STATE_DIR, capture_output=True, text=True, timeout=SMOKE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise StepFailed(f"smoke failed: pi did not answer within {SMOKE_TIMEOUT_SECONDS}s") from error
    if result.returncode != 0:
        raise StepFailed(f"smoke failed: pi exited {result.returncode}\n{result.stderr.strip()[-600:]}")
    replies = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    if not any(reply.get("type") == "response" and reply.get("success") and reply["data"]["commands"] for reply in replies):
        raise StepFailed("smoke failed: pi returned no command list")


def load_state() -> dict[str, dict[str, str]]:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"rejected": {}}


def save_state(state: dict[str, dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def notify(message: str) -> None:
    print(message)
    if shutil.which("osascript") is None:
        return
    script = f"display notification {json.dumps(message, ensure_ascii=False)} with title \"pi autoupdate\""
    subprocess.run(["osascript", "-e", script], capture_output=True)


def attempt(names: list[str], known_failing: set[str]) -> str | None:
    """Bump the named pins, verify, install and commit; on failure restore the previous pins and reinstall them.
    Returns why pi-straw-boss was held back at the install (a train started while the tests ran), else None."""
    before = {pin.name: pin.current for pin in collect_pins()}
    bump(names)
    changed = git("diff", "--name-only").splitlines()
    if not changed:
        return
    installed, late = False, None
    try:
        for command in test_commands():
            if command[-1] not in known_failing:
                step("tests", command)
        if SB_PIN in names and before[SB_PIN] != (bumped := {pin.name: pin.current for pin in collect_pins()})[SB_PIN] and (reason := train_hold()):
            # A train started while the tests ran: put the sb pin back, so the install leaves the server alone.
            sb = next(pin for pin in collect_pins() if pin.name == SB_PIN)
            rewrite(sb.quoted(bumped[SB_PIN]), sb.quoted(before[SB_PIN]))
            late = f"Held {SB_PIN}@{bumped[SB_PIN]}: {reason}; the next run tries it again."
            print(late)
            changed = git("diff", "--name-only").splitlines()
            if not changed:
                return late
        installed = True
        step("install", ["bash", str(ROOT / "scripts/install.sh")])
        smoke()
    except StepFailed:
        git("checkout", "--", *changed)
        if installed:
            try:
                step("restore install", ["bash", str(ROOT / "scripts/install.sh")])
            except StepFailed as error:
                raise RestoreFailed(str(error)) from error
        raise
    after = {pin.name: pin.current for pin in collect_pins()}
    moved = [name for name in names if after[name] != before[name]]
    subject = f"chore(pi): bump {moved[0]} to {after[moved[0]]}" if len(moved) == 1 else "chore(pi): bump pinned packages"
    git("add", *changed)
    git("commit", "-m", subject, "-m", "\n".join(f"{name} {before[name]} -> {after[name]}" for name in moved))
    return late


def train_hold() -> str | None:
    """Why a new pi-straw-boss must not be installed now, or None when no train runs (or no sb is installed to run one)."""
    if not SB_CLI.exists():
        return None
    result = subprocess.run(["node", str(SB_CLI), "train", "status", "--state", "live", "--json"], capture_output=True, text=True)
    try:
        trains = json.loads(result.stdout)["trains"] if result.returncode == 0 else None
    except (ValueError, KeyError, TypeError):
        trains = None
    if not isinstance(trains, list):
        return f"train status could not be read ({(result.stderr or result.stdout).strip()[:120] or f'exit {result.returncode}'})"
    if trains:
        names = ", ".join(f"{t.get('project')}/{t.get('app')} {t.get('code')}" for t in trains[:3] if isinstance(t, dict))
        return f"train {names} is live" if len(trains) == 1 else f"{len(trains)} trains are live ({names})"
    return None


def skip_reason() -> str | None:
    branch = git("branch", "--show-current")
    if branch != MAIN_BRANCH:
        return f"the checkout is on {branch or 'a detached HEAD'}, not {MAIN_BRANCH}"
    if git("status", "--porcelain"):
        return "the working tree has uncommitted changes"
    return None


def auto() -> None:
    print(f"== {datetime.now():%Y-%m-%d %H:%M:%S} pi-pins auto ==")
    if reason := skip_reason():
        notify(f"Skipped: {reason}.")
        return
    state = load_state()
    candidates = [pin for pin in collect_pins() if pin.kind != "git" and pin.name not in MANUAL_PINS]
    newest = dict(zip((pin.name for pin in candidates), latest_all(candidates), strict=True))
    due = [pin.name for pin in candidates if newest[pin.name] != pin.current and state["rejected"].get(pin.name) != newest[pin.name]]
    held = None
    if SB_PIN in due and (reason := train_hold()):
        due.remove(SB_PIN)
        held = f"Held {SB_PIN}@{newest[SB_PIN]}: {reason}; the next run tries it again."
        print(held)
    if not due:
        if held:
            notify(held)
        print("Every pin is current or already rejected at its latest version.")
        return
    known_failing = failing_tests()
    if known_failing:
        print(f"Tests failing before any bump, skipped as a gate: {', '.join(sorted(known_failing))}")
    updated: list[str] = []
    failures: dict[str, str] = {}
    try:
        if late := attempt(due, known_failing):
            held = late
        updated = [name for name in due if not (late and name == SB_PIN)]
    except StepFailed as error:
        print(error)
        if len(due) == 1:
            failures[due[0]] = str(error)
        else:
            print("Retrying each pin on its own to isolate the failure.")
            for name in due:
                try:
                    if late := attempt([name], known_failing):
                        held = late
                    else:
                        updated.append(name)
                except StepFailed as single:
                    failures[name] = str(single)
    for name, error in failures.items():
        state["rejected"][name] = newest[name]
        print(f"Rejected {name}@{newest[name]}: {error}")
    save_state(state)
    parts = [f"Updated {len(updated)}: {', '.join(updated)}." if updated else None,
             "Rejected: " + ", ".join(f"{name}@{newest[name]} ({error.splitlines()[0]})" for name, error in failures.items()) + "." if failures else None,
             f"{len(known_failing)} test file(s) were already failing." if known_failing else None, held]
    notify(" ".join(part for part in parts if part))


def tool_directories() -> list[str]:
    directories: list[str] = []
    for tool in (*REQUIRED_TOOLS, *OPTIONAL_TOOLS):
        found = shutil.which(tool)
        if found is None:
            if tool in REQUIRED_TOOLS:
                raise ValueError(f"{tool} is not on PATH; the schedule needs it")
            continue
        directory = str(Path(found).parent)
        if directory not in directories:
            directories.append(directory)
    return [*directories, *(path for path in SYSTEM_PATH if path not in directories)]


def launchd_plist() -> dict:
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "auto"],
        "StartCalendarInterval": SCHEDULE,
        "StandardOutPath": str(LOG_FILE),
        "StandardErrorPath": str(LOG_FILE),
        "EnvironmentVariables": {"PATH": ":".join(tool_directories()), "HOME": str(Path.home())},
    }


def launchctl(*args: str, check: bool = True) -> None:
    result = subprocess.run(["launchctl", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise ValueError(f"launchctl {' '.join(args)} failed: {result.stderr.strip()}")


def schedule() -> None:
    if sys.platform != "darwin":
        raise ValueError("schedule is macOS only (launchd): on this machine updates come from the provisioning playbook")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHD_PLIST.write_bytes(plistlib.dumps(launchd_plist()))
    domain = f"gui/{os.getuid()}"
    launchctl("bootout", f"{domain}/{LAUNCHD_LABEL}", check=False)
    launchctl("bootstrap", domain, str(LAUNCHD_PLIST))
    print(f"Scheduled daily at {SCHEDULE['Hour']:02d}:{SCHEDULE['Minute']:02d}: {LAUNCHD_PLIST}\nLog: {LOG_FILE}")


def unschedule() -> None:
    launchctl("bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}", check=False)
    LAUNCHD_PLIST.unlink(missing_ok=True)
    print(f"Removed {LAUNCHD_LABEL}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("outdated", help="compare every pin with its registry, remote HEAD, or newest tag that changed the plugin")
    bump_parser = commands.add_parser("bump", help="rewrite pins to the latest release; npm and Herdr plugin pins only unless named")
    bump_parser.add_argument("names", nargs="*", help="pinned package names, as `outdated` prints them")
    commands.add_parser("auto", help="bump every npm and Herdr plugin pin to its latest release, keep it only if tests, install and a pi load pass")
    commands.add_parser("forks", help="compare every fork pin with its upstream: drift, carried PRs, and what to do; exit 1 when any needs action")
    commands.add_parser("check", help="`outdated`, then `forks`")
    commands.add_parser("schedule", help="run `auto` daily through launchd")
    commands.add_parser("unschedule", help="remove the launchd schedule")
    args = parser.parse_args()
    if args.action == "outdated":
        outdated()
    elif args.action == "forks":
        sys.exit(forks())
    elif args.action == "check":
        outdated()
        print()
        sys.exit(forks())
    elif args.action == "auto":
        try:
            auto()
        except Exception as error:
            notify(f"Crashed: {str(error).splitlines()[0]} See {LOG_FILE}.")
            raise
    elif args.action == "schedule":
        schedule()
    elif args.action == "unschedule":
        unschedule()
    else:
        bump(args.names)


if __name__ == "__main__":
    main()
