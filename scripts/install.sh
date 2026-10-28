#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/python.sh
source "$SCRIPT_DIR/python.sh"
SKILLS_DIR="$REPO_ROOT/skills"
RULES_DIR="$REPO_ROOT/rules"
AGENTS_DIR="$REPO_ROOT/agents"
CODEBASE_MEMORY_INSTALL_URL="https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh"

OVERLAY_ROOT=""
SAVED_OVERLAY=""
NO_OVERLAY=0
TARGET_HOME="${HOME}"
FORCE=0
SKIP_EXTERNAL=0
BACKUP_ROOT=""

usage() {
  cat <<'EOF'
Usage: bash scripts/install.sh [--home PATH] [--force] [--skip-external] [--overlay PATH | --no-overlay]

Installs this repository's pi setup:
  - ~/.agents/skills/*/        links to skills/ (and the overlay's skills/)
  - ~/.pi/agent/rules          link to rules/
  - ~/.pi/agent/agents         link to agents/
  - ~/.local/bin/codebase-memory-mcp when missing
  - everything scripts/pi-target.py install manages: pi itself, its Herdr
    integration, pi packages, anchorloop, this repository's pi package, the
    generated ~/.pi/agent/AGENTS.md, model routing, UI settings,
    the overlay's optional plugins (when their checkouts exist), and team-toon-tack

Pass --skip-external to install configuration only, without npm, pi, Herdr,
or network installers.

--overlay PATH layers a second checkout over this one: its skills/ are linked
beside ours, its pi/AGENTS.append.md is appended to the generated AGENTS.md, and
its overlay.json may declare optional plugins. The WEIHUNG_OVERLAY variable
does the same. The install records the overlay, so a later install or uninstall
without --overlay keeps it; --no-overlay installs without it.

Defaults to failing on conflicts. Pass --force to back up conflicting targets
before replacing them.
EOF
}

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

ensure_backup_root() {
  if [[ -n "$BACKUP_ROOT" ]]; then
    return
  fi

  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  BACKUP_ROOT="$TARGET_HOME/.local/state/weihung-agent-root/backups/$stamp"
  mkdir -p "$BACKUP_ROOT"
}

backup_target() {
  local dest="$1"
  local rel_dest="${dest#"$TARGET_HOME"/}"

  ensure_backup_root
  mkdir -p "$BACKUP_ROOT/$(dirname "$rel_dest")"
  mv "$dest" "$BACKUP_ROOT/$rel_dest"
  log "Backed up $dest -> $BACKUP_ROOT/$rel_dest"
}

install_link() {
  local src="$1"
  local dest="$2"

  mkdir -p "$(dirname "$dest")"

  if [[ -L "$dest" ]] && [[ "$(readlink "$dest")" == "$src" ]]; then
    log "OK: $dest"
    return
  fi

  # A link into this checkout or its overlay is ours (a checkout that moved or was split leaves a stale one): re-point it.
  if [[ -L "$dest" ]] && is_managed_target "$(readlink "$dest")"; then
    rm "$dest"
    log "Re-pointed $dest"
  fi

  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ "$FORCE" -ne 1 ]]; then
      fail "$dest already exists. Re-run with --force to back it up and replace it."
    fi
    backup_target "$dest"
  fi

  ln -s "$src" "$dest"
  log "Linked $dest -> $src"
}

is_in_list() {
  local target="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$target" ]]; then
      return 0
    fi
  done
  return 1
}

is_managed_target() {
  local target="$1"
  [[ "$target" == "$REPO_ROOT"/* ]] && return 0
  # The recorded overlay counts too, so --no-overlay and a changed overlay still prune the links the old one made.
  [[ -n "$OVERLAY_ROOT" && "$target" == "$OVERLAY_ROOT"/* ]] && return 0
  [[ -n "$SAVED_OVERLAY" && "$target" == "$SAVED_OVERLAY"/* ]]
}

prune_managed_entries() {
  local target_dir="$1"
  shift
  local allowed=("$@")

  [[ -d "$target_dir" ]] || return 0

  while IFS= read -r link; do
    local link_name
    link_name="$(basename "$link")"
    local link_target
    link_target="$(readlink "$link" || true)"

    if is_managed_target "$link_target"; then
      if ! is_in_list "$link_name" ${allowed[@]+"${allowed[@]}"} || [[ ! -e "$link" ]]; then
        rm "$link"
        log "Pruned retired managed link $link"
      fi
    fi
  done < <(find "$target_dir" -maxdepth 1 -mindepth 1 -type l | sort)
}

# pi reads personal skills from ~/.agents/skills. Directory copies left there
# under a repository skill name are stale snapshots, so they move to the backup
# before the repository links take their place.
retire_skill_copies() {
  local skills_dir="$1"
  shift
  local name

  for name in "$@"; do
    if [[ -e "$skills_dir/$name" && ! -L "$skills_dir/$name" ]]; then
      backup_target "$skills_dir/$name"
    fi
  done
}

install_codebase_memory_mcp() {
  local bin_dir="$TARGET_HOME/.local/bin"

  if [[ -x "$bin_dir/codebase-memory-mcp" ]]; then
    log "OK: $bin_dir/codebase-memory-mcp"
    return
  fi

  # The upstream installer downloads a large binary, so a sandboxed run skips it. pi-target.py registers the
  # server with pi-mcp-adapter itself, which is why --skip-config keeps the installer out of other agents' configs.
  if [[ "$SKIP_EXTERNAL" -eq 1 ]]; then
    log "Skipping codebase-memory-mcp: --skip-external installs configuration only."
    return
  fi

  log "Installing codebase-memory-mcp from $CODEBASE_MEMORY_INSTALL_URL"
  curl -fsSL "$CODEBASE_MEMORY_INSTALL_URL" | bash -s -- --dir "$bin_dir" --skip-config
  if [[ ! -x "$bin_dir/codebase-memory-mcp" ]]; then
    log "codebase-memory-mcp install did not produce $bin_dir/codebase-memory-mcp"
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      [[ $# -ge 2 ]] || fail "--home requires a path"
      TARGET_HOME="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
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
    --no-overlay)
      NO_OVERLAY=1
      shift
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

SAVED_OVERLAY="$("$PYTHON" "$REPO_ROOT/scripts/pi-target.py" saved-overlay --home "$TARGET_HOME")"
if [[ "$NO_OVERLAY" -eq 1 ]]; then
  [[ -z "$OVERLAY_ROOT" ]] || fail "--overlay and --no-overlay cannot be combined"
  unset WEIHUNG_OVERLAY
else
  OVERLAY_ROOT="${OVERLAY_ROOT:-${WEIHUNG_OVERLAY:-}}"
  # No overlay given: keep the one the last install recorded.
  OVERLAY_ROOT="${OVERLAY_ROOT:-$SAVED_OVERLAY}"
fi
if [[ -n "$OVERLAY_ROOT" ]]; then
  [[ -d "$OVERLAY_ROOT" ]] || fail "overlay $OVERLAY_ROOT is not a directory; pass --overlay PATH, or --no-overlay to install without it"
  OVERLAY_ROOT="$(cd -- "$OVERLAY_ROOT" && pwd -P)"
  export WEIHUNG_OVERLAY="$OVERLAY_ROOT"
fi

# State and links from the repository's former name move first; the steps below use the new name.
"$PYTHON" "$REPO_ROOT/scripts/pi-target.py" migrate --home "$TARGET_HOME"

mkdir -p "$TARGET_HOME/.agents/skills"

root_skills=()
skill_sources=()
skill_roots=("$SKILLS_DIR")
if [[ -n "$OVERLAY_ROOT" && -d "$OVERLAY_ROOT/skills" ]]; then skill_roots+=("$OVERLAY_ROOT/skills"); fi
for skills_root in "${skill_roots[@]}"; do
  while IFS= read -r skill_dir; do
    skill_name="$(basename "$skill_dir")"
    if is_in_list "$skill_name" ${root_skills[@]+"${root_skills[@]}"}; then
      fail "skill $skill_name exists in both $SKILLS_DIR and the overlay"
    fi
    root_skills+=("$skill_name")
    skill_sources+=("$skill_dir")
  done < <(find "$skills_root" -maxdepth 1 -mindepth 1 \( -type d -o -type l \) | sort)
done

prune_managed_entries "$TARGET_HOME/.agents/skills" "${root_skills[@]}"
retire_skill_copies "$TARGET_HOME/.agents/skills" "${root_skills[@]}"

for index in "${!root_skills[@]}"; do
  install_link "${skill_sources[$index]}" "$TARGET_HOME/.agents/skills/${root_skills[$index]}"
done
install_link "$RULES_DIR" "$TARGET_HOME/.pi/agent/rules"
install_link "$AGENTS_DIR" "$TARGET_HOME/.pi/agent/agents"

install_codebase_memory_mcp

pi_args=(install --home "$TARGET_HOME")
if [[ "$NO_OVERLAY" -eq 1 ]]; then pi_args+=(--no-overlay); fi
if [[ "$SKIP_EXTERNAL" -eq 1 ]]; then pi_args+=(--skip-external); fi
if [[ "$FORCE" -eq 1 ]]; then pi_args+=(--force); fi
"$PYTHON" "$REPO_ROOT/scripts/pi-target.py" "${pi_args[@]}"

log "Install complete."
