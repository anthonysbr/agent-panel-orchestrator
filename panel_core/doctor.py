from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from . import __version__
from .paths import resolve_panel_executable, resolve_project_root
from .providers import ProviderRegistry


def detect_install_source() -> str:
    package_dir = Path(__file__).resolve().parent
    if (package_dir / "_bundle" / "config" / "agents.json").is_file():
        return "pip"

    root = resolve_project_root()
    exe = resolve_panel_executable()
    exe_text = str(exe)
    if "node_modules" in exe_text or exe.name.endswith(".cjs"):
        return "npm"
    if (root / "panel").is_file() and (root / ".git").is_dir():
        return "git"
    if (root / "panel").is_file():
        return "git"
    return "unknown"


def run_doctor(registry: ProviderRegistry) -> Dict[str, Any]:
    version_info = sys.version_info
    python_ok = version_info >= (3, 10)
    providers: List[Dict[str, Any]] = []
    available_count = 0
    for name, detected in registry.detect_providers().items():
        entry = {
            "name": name,
            "available": detected.available,
            "path": detected.path,
            "version": detected.version,
        }
        providers.append(entry)
        if detected.available:
            available_count += 1

    checks = {
        "python": {
            "ok": python_ok,
            "version": f"{version_info.major}.{version_info.minor}.{version_info.micro}",
            "required": ">=3.10",
        },
        "install": {
            "ok": True,
            "source": detect_install_source(),
            "executable": str(resolve_panel_executable()),
        },
        "providers": {
            "ok": available_count > 0,
            "available": available_count,
            "items": providers,
        },
        "panel_version": __version__,
    }
    checks["ok"] = python_ok and available_count > 0
    return checks
