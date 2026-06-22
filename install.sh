#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${PANEL_INSTALL_DIR:-$HOME/.local/bin}"
LINK_PATH="$TARGET_DIR/panel"
SOURCE_PATH="$ROOT/panel"
MODE="install"

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--dry-run] [--check]

Creates a symlink:
  ~/.local/bin/panel -> <project>/panel

Options:
  --dry-run  Print the planned action without changing files.
  --check    Verify whether the symlink already points to this project.

Set PANEL_INSTALL_DIR to use a different bin directory.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      ;;
    --check)
      MODE="check"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install.sh: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ ! -x "$SOURCE_PATH" ]; then
  echo "install.sh: panel executable is missing or not executable: $SOURCE_PATH" >&2
  exit 1
fi

if [ "$MODE" = "check" ]; then
  if [ -L "$LINK_PATH" ] && [ "$(readlink "$LINK_PATH")" = "$SOURCE_PATH" ]; then
    echo "panel is installed: $LINK_PATH -> $SOURCE_PATH"
    exit 0
  fi
  echo "panel is not installed at $LINK_PATH"
  exit 1
fi

echo "Target directory: $TARGET_DIR"
echo "Symlink: $LINK_PATH -> $SOURCE_PATH"

if [ "$MODE" = "dry-run" ]; then
  echo "Dry run complete. No files changed."
  exit 0
fi

mkdir -p "$TARGET_DIR"
ln -sfn "$SOURCE_PATH" "$LINK_PATH"
echo "Installed panel at $LINK_PATH"
