from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


DEFAULT_GATES = [
    {"name": "compileall", "command": "python3 -m compileall panel_core tests -q"},
    {"name": "unittest", "command": "python3 -m unittest discover tests -q"},
]


@dataclass(frozen=True)
class GateResult:
    name: str
    command: str
    passed: bool
    returncode: Optional[int]
    output: str


@dataclass(frozen=True)
class GateRunSummary:
    passed: bool
    results: List[GateResult]


def gates_config_path(project_root: Path) -> Path:
    return project_root / ".panel" / "gates.yaml"


def load_gate_specs(project_root: Path) -> List[Dict[str, str]]:
    path = gates_config_path(project_root)
    if not path.is_file():
        return list(DEFAULT_GATES)
    raw = _parse_gates_file(path)
    gates = raw.get("gates", raw if isinstance(raw, list) else None)
    if not isinstance(gates, list) or not gates:
        return list(DEFAULT_GATES)
    specs: List[Dict[str, str]] = []
    for item in gates:
        if not isinstance(item, Mapping):
            raise ValueError(f"each gate must be an object in {path}")
        name = str(item.get("name", "")).strip()
        command = str(item.get("command", "")).strip()
        if not name or not command:
            raise ValueError(f"gate entries require name and command in {path}")
        specs.append({"name": name, "command": command})
    return specs


def run_gates(project_root: Path, specs: Optional[Sequence[Mapping[str, str]]] = None) -> GateRunSummary:
    root = project_root.resolve()
    gate_specs = list(specs) if specs is not None else load_gate_specs(root)
    results: List[GateResult] = []
    for spec in gate_specs:
        name = str(spec["name"])
        command = str(spec["command"])
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(root),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=600,
                check=False,
            )
            output = (completed.stdout or "").strip()
            passed = completed.returncode == 0
            results.append(
                GateResult(
                    name=name,
                    command=command,
                    passed=passed,
                    returncode=completed.returncode,
                    output=output,
                )
            )
        except subprocess.TimeoutExpired as exc:
            output = str(exc.stdout or exc) if hasattr(exc, "stdout") else str(exc)
            results.append(
                GateResult(
                    name=name,
                    command=command,
                    passed=False,
                    returncode=None,
                    output=output,
                )
            )
    return GateRunSummary(passed=all(item.passed for item in results), results=results)


def write_gate_report(run_dir: Path, round_dir: Path, summary: GateRunSummary) -> Path:
    report_path = round_dir / "gates.json"
    payload: Dict[str, Any] = {
        "passed": summary.passed,
        "results": [asdict(item) for item in summary.results],
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return report_path


def render_gate_report(summary: GateRunSummary) -> str:
    lines = ["# Gate Results", ""]
    if not summary.results:
        lines.append("No gates configured.")
        return "\n".join(lines) + "\n"
    for item in summary.results:
        status = "pass" if item.passed else "fail"
        lines.append(f"- {item.name}: {status} (`{item.command}`)")
        if not item.passed and item.output:
            lines.append(f"  ```")
            lines.append(item.output[:2000])
            lines.append("  ```")
    lines.append("")
    lines.append(f"Overall: {'pass' if summary.passed else 'fail'}")
    return "\n".join(lines) + "\n"


def _parse_gates_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".json", ".jsonl"}:
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_simple_yaml(text)
    return yaml.safe_load(text) or {}


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    gates: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- name:"):
            if current:
                gates.append(current)
            current = {"name": stripped.split(":", 1)[1].strip().strip('"').strip("'")}
            continue
        if stripped.startswith("name:") and not current:
            current["name"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            continue
        if stripped.startswith("command:"):
            current["command"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            continue
    if current:
        gates.append(current)
    return {"gates": gates}
