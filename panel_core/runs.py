from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    mode: str
    panel_slug: str
    judge: str
    dry_run: bool
    skills: List[str]
    status: str
    path: Path


@dataclass(frozen=True)
class AuditRoundSummary:
    round_number: int
    round_status: str
    builder_status: str
    gates_passed: bool
    clean: bool


@dataclass(frozen=True)
class RunDetail:
    summary: RunSummary
    status: str
    final_output: Optional[str]
    run_error: str
    stopped_reason: str
    audit_rounds: List[AuditRoundSummary]
    artifacts: Dict[str, str]


def _load_run_status(run_path: Path, mode: str) -> tuple[str, str, str, List[AuditRoundSummary]]:
    audit_summary_path = run_path / "audit_summary.json"
    if mode == "audit-loop" and audit_summary_path.is_file():
        audit = json.loads(audit_summary_path.read_text(encoding="utf-8"))
        stopped = str(audit.get("stopped_reason", "unknown"))
        status = "clean" if stopped == "clean" else stopped
        rounds = [
            AuditRoundSummary(
                round_number=int(item.get("round", 0)),
                round_status=str(item.get("round_status", "completed")),
                builder_status=str(item.get("builder_status", "")),
                gates_passed=bool(item.get("gates_passed")),
                clean=bool(item.get("clean")),
            )
            for item in audit.get("rounds_detail", [])
        ]
        return status, "", stopped, rounds

    graph_path = run_path / "task_graph.json"
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        status = str(graph.get("summary", {}).get("judge_status", "unknown"))
        run_error = str(graph.get("summary", {}).get("run_error", ""))
        return status, run_error, "", []

    return "unknown", "", "", []


def list_runs(runs_dir: Path) -> List[RunSummary]:
    if not runs_dir.is_dir():
        return []

    summaries: List[RunSummary] = []
    for child in sorted(runs_dir.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        plan_path = child / "run_plan.json"
        if not plan_path.is_file():
            continue
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        mode = str(raw.get("mode", "run"))
        status, _, _, _ = _load_run_status(child, mode)
        summaries.append(
            RunSummary(
                run_id=child.name,
                mode=mode,
                panel_slug=str(raw.get("panel_slug", "")),
                judge=str(raw.get("judge", "")),
                dry_run=bool(raw.get("dry_run")),
                skills=list(raw.get("skills", [])),
                status=status,
                path=child,
            )
        )
    return summaries


def load_run(runs_dir: Path, run_id: str) -> RunDetail:
    run_path = runs_dir / run_id
    if not run_path.is_dir():
        raise FileNotFoundError(f"run not found: {run_id}")

    plan_path = run_path / "run_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"run plan missing: {plan_path}")

    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    mode = str(raw.get("mode", "run"))
    status, run_error, stopped_reason, audit_rounds = _load_run_status(run_path, mode)
    summary = RunSummary(
        run_id=run_id,
        mode=mode,
        panel_slug=str(raw.get("panel_slug", "")),
        judge=str(raw.get("judge", "")),
        dry_run=bool(raw.get("dry_run")),
        skills=list(raw.get("skills", [])),
        status=status,
        path=run_path,
    )

    final_path = run_path / "final.md"
    final_output = str(final_path) if final_path.is_file() else None

    artifacts = {
        "run_plan": str(plan_path),
        "task_graph": str(run_path / "task_graph.json") if (run_path / "task_graph.json").is_file() else "",
        "task": str(run_path / "task.md"),
        "final": final_output or "",
        "verification": str(run_path / "verification.md") if (run_path / "verification.md").is_file() else "",
        "decision": str(run_path / "decision.md") if (run_path / "decision.md").is_file() else "",
        "learning": str(run_path / "learning.md") if (run_path / "learning.md").is_file() else "",
        "audit_loop": str(run_path / "audit_loop.json") if (run_path / "audit_loop.json").is_file() else "",
        "audit_summary": str(run_path / "audit_summary.json") if (run_path / "audit_summary.json").is_file() else "",
    }

    return RunDetail(
        summary=summary,
        status=status,
        final_output=final_output,
        run_error=run_error,
        stopped_reason=stopped_reason,
        audit_rounds=audit_rounds,
        artifacts=artifacts,
    )


def run_summary_to_dict(summary: RunSummary) -> Dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "mode": summary.mode,
        "panel_slug": summary.panel_slug,
        "judge": summary.judge,
        "dry_run": summary.dry_run,
        "skills": summary.skills,
        "status": summary.status,
        "path": str(summary.path),
    }


def run_detail_to_dict(detail: RunDetail) -> Dict[str, Any]:
    payload = run_summary_to_dict(detail.summary)
    payload.update(
        {
            "status": detail.status,
            "final_output": detail.final_output,
            "run_error": detail.run_error,
            "stopped_reason": detail.stopped_reason,
            "audit_rounds": [
                {
                    "round": item.round_number,
                    "round_status": item.round_status,
                    "builder_status": item.builder_status,
                    "gates_passed": item.gates_passed,
                    "clean": item.clean,
                }
                for item in detail.audit_rounds
            ],
            "artifacts": detail.artifacts,
        }
    )
    return payload
