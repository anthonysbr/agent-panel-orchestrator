from __future__ import annotations

import os
import shutil
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def resolve_project_root() -> Path:
    repo_root = _PACKAGE_DIR.parent
    if (repo_root / "config" / "agents.json").is_file():
        return repo_root

    bundle_root = _PACKAGE_DIR / "_bundle"
    if (bundle_root / "config" / "agents.json").is_file():
        return bundle_root

    raise RuntimeError("agent-panel-orchestrator install is missing bundled config")


def resolve_panel_executable() -> Path:
    override = os.environ.get("PANEL_EXECUTABLE")
    if override:
        return Path(override).expanduser().resolve()

    root = resolve_project_root()
    repo_panel = root / "panel"
    if repo_panel.is_file():
        return repo_panel.resolve()

    found = shutil.which("panel")
    if found:
        return Path(found).resolve()

    return Path("panel")


PROJECT_ROOT = resolve_project_root()
