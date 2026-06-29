from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .gates import gates_config_path, load_gate_specs
from .paths import resolve_panel_executable, resolve_project_root
from .providers import ProviderRegistry

PROVIDER_HINTS = {
    "codex": "Install Codex CLI and ensure `codex` is on PATH.",
    "claude": "Install Claude Code and ensure `claude` is on PATH.",
    "cursor": "Install Cursor Agent CLI; the binary name is `agent`, not `cursor`.",
    "gemini": "Install Gemini CLI and ensure `gemini` is on PATH.",
}


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


def run_doctor(registry: ProviderRegistry, project_root: Optional[Path] = None) -> Dict[str, Any]:
    root = (project_root or Path.cwd()).resolve()
    version_info = sys.version_info
    python_ok = version_info >= (3, 10)
    providers: List[Dict[str, Any]] = []
    available_count = 0
    for name, detected in registry.detect_providers().items():
        hint = "" if detected.available else PROVIDER_HINTS.get(name, "")
        entry = {
            "name": name,
            "available": detected.available,
            "path": detected.path,
            "version": detected.version,
            "hint": hint,
        }
        providers.append(entry)
        if detected.available:
            available_count += 1

    gates_path = gates_config_path(root)
    gates_configured = gates_path.is_file()
    gate_names: List[str] = []
    gates_ok = True
    gates_hint = ""
    try:
        gate_names = [spec["name"] for spec in load_gate_specs(root)]
    except ValueError as exc:
        gates_ok = False
        gates_hint = str(exc)
    if not gates_configured:
        example = root / ".panel" / "gates.yaml.example"
        if example.is_file():
            gates_hint = f"No .panel/gates.yaml; copy {example.name} to gates.yaml for audit-loop."
        else:
            gates_hint = "No .panel/gates.yaml; audit-loop uses built-in compileall + unittest defaults."

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
        "gates": {
            "ok": gates_ok,
            "configured": gates_configured,
            "path": str(gates_path),
            "gates": gate_names,
            "hint": gates_hint,
        },
        "panel_version": __version__,
    }
    checks["ok"] = python_ok and available_count > 0 and gates_ok
    return checks
