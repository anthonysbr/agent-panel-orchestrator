#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT="$ROOT/pyproject.toml"
INIT="$ROOT/panel_core/__init__.py"
NPM="$ROOT/npm/package.json"

read_version() {
  local file="$1"
  local pattern="$2"
  grep -E "$pattern" "$file" | head -1 | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/'
}

V1="$(read_version "$PYPROJECT" '^version = ')"
V2="$(read_version "$INIT" '__version__ = ')"
V3="$(grep -E '"version":' "$NPM" | head -1 | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"

if [[ "$V1" != "$V2" || "$V1" != "$V3" ]]; then
  echo "version mismatch: pyproject=$V1 __init__=$V2 npm=$V3" >&2
  exit 1
fi

echo "version ok: $V1"
