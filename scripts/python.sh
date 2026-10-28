#!/usr/bin/env bash
# Sourced by install.sh and uninstall.sh: sets PYTHON to an interpreter that runs scripts/pi_root.
#
# pi_root needs Python 3.10 or newer. A bare `python3` can be older: macOS ships 3.9 in /usr/bin,
# and Homebrew's versioned python@3.x formulae no longer link an unversioned `python3` into its bin.
# WEIHUNG_PYTHON names one interpreter to use instead of searching.

set -euo pipefail

python_ok() {
  "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null
}

find_python() {
  if [[ -n "${WEIHUNG_PYTHON:-}" ]]; then
    if python_ok "$WEIHUNG_PYTHON"; then
      printf '%s\n' "$WEIHUNG_PYTHON"
      return 0
    fi
    echo "WEIHUNG_PYTHON=$WEIHUNG_PYTHON is not Python 3.10 or newer" >&2
    return 1
  fi
  local candidate
  for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  echo "Python 3.10 or newer is required (python3 is $(python3 --version 2>&1 || echo missing)); install it, e.g. brew install python@3.14, or set WEIHUNG_PYTHON" >&2
  return 1
}

PYTHON="$(find_python)"
