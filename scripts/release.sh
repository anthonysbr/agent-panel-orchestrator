#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-}"

if [ -z "$VERSION" ]; then
  VERSION="$(python3 -c "from panel_core import __version__; print(__version__)")"
fi

DIST="$ROOT/dist"
RELEASE="$DIST/release"
PY_WHEEL="$DIST/wheels"
NPM_DIR="$ROOT/npm"
WIN_DIR="$RELEASE/agent-panel-orchestrator-windows-$VERSION"

rm -rf "$RELEASE" "$PY_WHEEL"
mkdir -p "$PY_WHEEL" "$RELEASE"

echo "==> Building Python wheel ($VERSION)"
BUILD_VENV="$(mktemp -d)"
python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/pip" install --quiet build hatchling
"$BUILD_VENV/bin/python" -m build --wheel --outdir "$PY_WHEEL"
rm -rf "$BUILD_VENV"

echo "==> Building npm package ($VERSION)"
node "$NPM_DIR/scripts/prepack.js"
(
  cd "$NPM_DIR"
  npm pack --silent
  mv agent-panel-orchestrator-"$VERSION".tgz "$RELEASE/"
)

echo "==> Building Windows zip ($VERSION)"
mkdir -p "$WIN_DIR"
cp -R "$NPM_DIR/python" "$WIN_DIR/python"
cp "$ROOT/packaging/windows/panel.cmd" "$WIN_DIR/panel.cmd"
cp "$ROOT/packaging/windows/install.ps1" "$WIN_DIR/install.ps1"
(
  cd "$RELEASE"
  zip -qr "agent-panel-orchestrator-windows-$VERSION.zip" "agent-panel-orchestrator-windows-$VERSION"
)

echo "==> Release artifacts"
ls -1 "$PY_WHEEL" "$RELEASE"

TARBALL_URL="https://github.com/anthonysbr/agent-panel-orchestrator/archive/refs/tags/v$VERSION.tar.gz"
echo
echo "Update Homebrew sha256:"
echo "  curl -L $TARBALL_URL | shasum -a 256"
echo
echo "Update winget InstallerSha256:"
echo "  shasum -a 256 $RELEASE/agent-panel-orchestrator-windows-$VERSION.zip"
