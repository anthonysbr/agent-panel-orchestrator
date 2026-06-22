from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    panel_slug: str
    judge: str
    dry_run: bool
    skills: List[str]
    path: Path


@dataclass(frozen=True)
class RunDetail:
    summary: RunSummary
    status: str
    final_output: Optional[str]
    run_error: str
    artifacts: Dict[str, str]


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
        summaries.append(
            RunSummary(
                run_id=child.name,
                panel_slug=str(raw.get("panel_slug", "")),
                judge=str(raw.get("judge", "")),
                dry_run=bool(raw.get("dry_run")),
                skills=list(raw.get("skills", [])),
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
    summary = RunSummary(
        run_id=run_id,
        panel_slug=str(raw.get("panel_slug", "")),
        judge=str(raw.get("judge", "")),
        dry_run=bool(raw.get("dry_run")),
        skills=list(raw.get("skills", [])),
        path=run_path,
    )

    status = "unknown"
    run_error = ""
    graph_path = run_path / "task_graph.json"
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        status = str(graph.get("summary", {}).get("judge_status", "unknown"))
        run_error = str(graph.get("summary", {}).get("run_error", ""))

    final_path = run_path / "final.md"
    final_output = str(final_path) if final_path.is_file() else None

    artifacts = {
        "run_plan": str(plan_path),
        "task_graph": str(graph_path) if graph_path.is_file() else "",
        "task": str(run_path / "task.md"),
        "final": final_output or "",
        "verification": str(run_path / "verification.md") if (run_path / "verification.md").is_file() else "",
        "decision": str(run_path / "decision.md") if (run_path / "decision.md").is_file() else "",
        "learning": str(run_path / "learning.md") if (run_path / "learning.md").is_file() else "",
    }

    return RunDetail(
        summary=summary,
        status=status,
        final_output=final_output,
        run_error=run_error,
        artifacts=artifacts,
    )


def run_summary_to_dict(summary: RunSummary) -> Dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "panel_slug": summary.panel_slug,
        "judge": summary.judge,
        "dry_run": summary.dry_run,
        "skills": summary.skills,
        "path": str(summary.path),
    }


def run_detail_to_dict(detail: RunDetail) -> Dict[str, Any]:
    payload = run_summary_to_dict(detail.summary)
    payload.update(
        {
            "status": detail.status,
            "final_output": detail.final_output,
            "run_error": detail.run_error,
            "artifacts": detail.artifacts,
        }
    )
    return payload
