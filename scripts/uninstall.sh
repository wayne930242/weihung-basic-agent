#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/python.sh
source "$SCRIPT_DIR/python.sh"
SKILLS_DIR="$REPO_ROOT/skills"

TARGET_HOME="${HOME}"
BACKUP_BASE="${TARGET_HOME}/.local/state/weihung-agent-root/backups"
SKIP_EXTERNAL=0
OVERLAY_ROOT=""

usage() {
  cat <<'EOF'
Usage: bash scripts/uninstall.sh [--home PATH] [--skip-external] [--overlay PATH]

Uninstall flow:
  - restore each managed link from the latest backup directory when a backup exists
  - otherwise remove the repository links in ~/.agents/skills, ~/.pi/agent/rules,
    and ~/.pi/agent/agents
  - run scripts/pi-target.py uninstall, which removes this repository's pi
    packages and resources and restores the pi settings it changed

--overlay PATH (or WEIHUNG_OVERLAY) names the overlay install.sh was given.
Without it, uninstall uses the overlay the install recorded; the overlay's skill
links and optional plugins are removed with ours.

The pi binary and its login state stay installed.
EOF
}

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

# Install runs write their backups under per-second stamps, so the newest stamp
# holding this path is the one to restore, not the newest stamp overall.
backup_for() {
  local rel_dest="$1"
  [[ -d "$BACKUP_BASE" ]] || return 0
  local dir
  while IFS= read -r dir; do
    if [[ -e "$dir/$rel_dest" || -L "$dir/$rel_dest" ]]; then
      printf '%s\n' "$dir/$rel_dest"
      return 0
    fi
  done < <(find "$BACKUP_BASE" -mindepth 1 -maxdepth 1 -type d | sort -r)
}

restore_or_remove() {
  local dest="$1"
  local rel_dest="${dest#"$TARGET_HOME"/}"
  local backup_path
  backup_path="$(backup_for "$rel_dest")"

  if [[ -n "$backup_path" ]]; then
    if [[ -L "$dest" ]]; then
      rm "$dest"
    elif [[ -e "$dest" ]]; then
      fail "refusing to overwrite non-symlink at $dest while restoring backup"
    fi

    mkdir -p "$(dirname "$dest")"
    cp -a "$backup_path" "$dest"
    log "Restored $dest from $backup_path"
    return
  fi

  if [[ -L "$dest" ]]; then
    rm "$dest"
    log "Removed $dest"
  fi
}

prune_managed_links() {
  local target_dir="$1"
  [[ -d "$target_dir" ]] || return 0

  while IFS= read -r link; do
    local link_target
    link_target="$(readlink "$link" || true)"

    if [[ "$link_target" == "$REPO_ROOT"/* || ( -n "$OVERLAY_ROOT" && "$link_target" == "$OVERLAY_ROOT"/* ) ]]; then
      restore_or_remove "$link"
    fi
  done < <(find "$target_dir" -maxdepth 1 -mindepth 1 -type l | sort)
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      [[ $# -ge 2 ]] || fail "--home requires a path"
      TARGET_HOME="$2"
      BACKUP_BASE="${TARGET_HOME}/.local/state/weihung-agent-root/backups"
      shift 2
      ;;
    --skip-external)
      SKIP_EXTERNAL=1
      shift
      ;;
    --overlay)
      [[ $# -ge 2 ]] || fail "--overlay requires a path"
      OVERLAY_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

OVERLAY_ROOT="${OVERLAY_ROOT:-${WEIHUNG_OVERLAY:-}}"
# No overlay given: remove the one the install recorded, even if its checkout is gone.
OVERLAY_ROOT="${OVERLAY_ROOT:-$("$PYTHON" "$REPO_ROOT/scripts/pi-target.py" saved-overlay --home "$TARGET_HOME")}"
if [[ -n "$OVERLAY_ROOT" ]]; then
  if [[ -d "$OVERLAY_ROOT" ]]; then OVERLAY_ROOT="$(cd -- "$OVERLAY_ROOT" && pwd -P)"; fi
  export WEIHUNG_OVERLAY="$OVERLAY_ROOT"
fi

# State and links from the repository's former name move first; the steps below use the new name.
"$PYTHON" "$REPO_ROOT/scripts/pi-target.py" migrate --home "$TARGET_HOME"

while IFS= read -r skill_dir; do
  restore_or_remove "$TARGET_HOME/.agents/skills/$(basename "$skill_dir")"
done < <(find "$SKILLS_DIR" -maxdepth 1 -mindepth 1 -type d | sort)
if [[ -n "$OVERLAY_ROOT" && -d "$OVERLAY_ROOT/skills" ]]; then
  while IFS= read -r skill_dir; do
    restore_or_remove "$TARGET_HOME/.agents/skills/$(basename "$skill_dir")"
  done < <(find "$OVERLAY_ROOT/skills" -maxdepth 1 -mindepth 1 -type d | sort)
fi
prune_managed_links "$TARGET_HOME/.agents/skills"
if [[ -L "$TARGET_HOME/.pi/agent/rules" && "$(readlink "$TARGET_HOME/.pi/agent/rules")" == "$REPO_ROOT/rules" ]]; then
  restore_or_remove "$TARGET_HOME/.pi/agent/rules"
fi
if [[ -L "$TARGET_HOME/.pi/agent/agents" && "$(readlink "$TARGET_HOME/.pi/agent/agents")" == "$REPO_ROOT/agents" ]]; then
  restore_or_remove "$TARGET_HOME/.pi/agent/agents"
fi

pi_args=(uninstall --home "$TARGET_HOME")
if [[ "$SKIP_EXTERNAL" -eq 1 ]]; then pi_args+=(--skip-external); fi
"$PYTHON" "$REPO_ROOT/scripts/pi-target.py" "${pi_args[@]}"

rmdir "$TARGET_HOME/.agents/skills" "$TARGET_HOME/.agents" 2>/dev/null || true

log "Uninstall complete."
