from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .providers import ProviderRunResult


SCHEMA_VERSION = 1


def write_run_contract(
    run_dir: Path,
    task: str,
    plan: Any,
    panel_results: Optional[Sequence[ProviderRunResult]] = None,
    judge_result: Optional[ProviderRunResult] = None,
    final_output_path: Optional[Path] = None,
    run_error: str = "",
) -> None:
    panel_results = list(panel_results or [])
    graph = build_task_graph(
        run_dir=run_dir,
        task=task,
        plan=plan,
        panel_results=panel_results,
        judge_result=judge_result,
        final_output_path=final_output_path,
        run_error=run_error,
    )
    (run_dir / "task_graph.json").write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    (run_dir / "verification.md").write_text(
        render_verification(task, plan, panel_results, judge_result, final_output_path, run_error),
        encoding="utf-8",
    )
    (run_dir / "decision.md").write_text(
        render_decision(plan, panel_results, judge_result, final_output_path, run_error),
        encoding="utf-8",
    )
    (run_dir / "learning.md").write_text(
        render_learning(plan, panel_results, judge_result, run_error),
        encoding="utf-8",
    )


def build_task_graph(
    run_dir: Path,
    task: str,
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    final_output_path: Optional[Path],
    run_error: str,
) -> Dict[str, Any]:
    panelists = list(getattr(plan, "panelists"))
    result_pairs = _panel_result_pairs(panelists, panel_results)
    dry_run = bool(getattr(plan, "dry_run"))
    terminal = dry_run or bool(run_error) or judge_result is not None
    successful_panelists = [panelist for panelist, result in result_pairs if result and result.status == "success"]

    nodes: List[Dict[str, Any]] = [
        {
            "id": "intake",
            "type": "intake",
            "status": "complete",
            "artifacts": ["task.md", "run_plan.json"],
        }
    ]
    for panelist, result in result_pairs:
        panelist_id = getattr(panelist, "panelist_id")
        status = _panelist_status(dry_run, result)
        artifacts = [f"panelists/{panelist_id}.prompt.md"]
        if result is not None:
            artifacts.append(f"panelists/{panelist_id}.output.md")
            artifacts.append(f"logs/{panelist_id}.log")
        nodes.append(
            {
                "id": f"panelist:{panelist_id}",
                "type": "panelist",
                "panelist_id": panelist_id,
                "provider": getattr(panelist, "provider"),
                "status": status,
                "artifacts": artifacts,
            }
        )

    nodes.append(
        {
            "id": "judge",
            "type": "judge",
            "provider": getattr(plan, "judge"),
            "status": _judge_status(dry_run, panel_results, judge_result, run_error),
            "artifacts": _judge_artifacts(judge_result, final_output_path),
        }
    )
    nodes.append(
        {
            "id": "verification",
            "type": "verification",
            "status": _verification_status(dry_run, terminal, judge_result, run_error),
            "artifacts": ["verification.md"],
        }
    )
    nodes.append(
        {
            "id": "learning",
            "type": "learning",
            "status": _learning_status(dry_run, terminal),
            "artifacts": ["learning.md"],
        }
    )

    edges = [{"from": "intake", "to": f"panelist:{getattr(panelist, 'panelist_id')}"} for panelist in panelists]
    edges.extend({"from": f"panelist:{getattr(panelist, 'panelist_id')}", "to": "judge"} for panelist in panelists)
    edges.extend(
        [
            {"from": "judge", "to": "verification"},
            {"from": "verification", "to": "learning"},
        ]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "goal": task,
        "dry_run": dry_run,
        "run_dir": str(run_dir),
        "panel_slug": getattr(plan, "panel_slug"),
        "judge": getattr(plan, "judge"),
        "skills": list(getattr(plan, "skills", [])),
        "summary": {
            "panelists_total": len(panelists),
            "panelists_successful": len(successful_panelists),
            "judge_status": judge_result.status if judge_result else _judge_status(dry_run, panel_results, judge_result, run_error),
            "run_error": run_error,
            "final_output": str(final_output_path) if final_output_path else "",
        },
        "nodes": nodes,
        "edges": edges,
    }


def render_verification(
    task: str,
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    final_output_path: Optional[Path],
    run_error: str,
) -> str:
    lines = [
        "# Verification",
        "",
        f"Status: {_verification_label(plan, panel_results, judge_result, run_error)}",
        "",
        "## Goal",
        task,
        "",
        "## Evidence",
        "- Run plan: `run_plan.json`",
        "- Task: `task.md`",
    ]
    for panelist, result in _panel_result_pairs(list(getattr(plan, "panelists")), panel_results):
        panelist_id = getattr(panelist, "panelist_id")
        if result is None:
            status = "dry-run" if getattr(plan, "dry_run") else "not run yet"
        else:
            status = result.status
        lines.append(f"- Panelist `{panelist_id}` ({getattr(panelist, 'provider')}): {status}")
    if judge_result is None:
        judge_status = "dry-run" if getattr(plan, "dry_run") else "not completed"
    else:
        judge_status = judge_result.status
    lines.extend(
        [
            f"- Judge `{getattr(plan, 'judge')}`: {judge_status}",
            f"- Final output: `{_relative_or_missing(final_output_path)}`",
            "",
            "## Limitations",
        ]
    )
    lines.extend(_limitations(plan, panel_results, judge_result, run_error))
    return "\n".join(lines).rstrip() + "\n"


def render_decision(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    final_output_path: Optional[Path],
    run_error: str,
) -> str:
    considered, ignored = _panelist_groups(plan, panel_results)
    lines = [
        "# Decision",
        "",
        f"Decision status: {_decision_status(plan, panel_results, judge_result, run_error)}",
        f"Panel: `{getattr(plan, 'panel_slug')}`",
        f"Judge: `{getattr(plan, 'judge')}`",
        f"Final output: `{_relative_or_missing(final_output_path)}`",
        "",
        "## Panelists Considered",
    ]
    lines.extend(_list_or_none(considered))
    lines.append("")
    lines.append("## Panelists Ignored")
    lines.extend(_list_or_none(ignored))
    lines.extend(["", "## Summary", _decision_summary(plan, panel_results, judge_result, run_error)])
    return "\n".join(lines).rstrip() + "\n"


def render_learning(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    failed_panelists = [result for result in panel_results if result.status != "success"]
    lines = [
        "# Learning",
        "",
        f"Run mode: {'dry-run' if getattr(plan, 'dry_run') else 'live'}",
        "",
        "## Observations",
    ]
    if getattr(plan, "dry_run"):
        lines.append("- The run plan and prompts were generated without provider calls.")
    elif run_error:
        lines.append(f"- The run stopped before completion: {run_error}")
    elif judge_result and judge_result.status == "success":
        lines.append("- The panel and judge loop completed with a final output.")
    else:
        lines.append("- The run has not completed yet.")

    if failed_panelists:
        lines.append(f"- Non-success panelist results: {len(failed_panelists)}.")
    if judge_result and judge_result.status != "success":
        lines.append(f"- Judge result was `{judge_result.status}`.")

    lines.extend(["", "## Guardrail Recommendation"])
    lines.append(_guardrail_recommendation(plan, panel_results, judge_result, run_error))
    return "\n".join(lines).rstrip() + "\n"


def _panel_result_pairs(panelists: Sequence[Any], panel_results: Sequence[ProviderRunResult]) -> List[Tuple[Any, Optional[ProviderRunResult]]]:
    pairs: List[Tuple[Any, Optional[ProviderRunResult]]] = []
    for index, panelist in enumerate(panelists):
        result = panel_results[index] if index < len(panel_results) else None
        pairs.append((panelist, result))
    return pairs


def _panelist_status(dry_run: bool, result: Optional[ProviderRunResult]) -> str:
    if result is None:
        return "dry_run" if dry_run else "planned"
    return result.status


def _judge_status(
    dry_run: bool,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if judge_result is not None:
        return judge_result.status
    if dry_run:
        return "dry_run"
    if run_error:
        return "blocked"
    if panel_results and not any(result.status == "success" for result in panel_results):
        return "blocked"
    return "planned"


def _verification_status(
    dry_run: bool,
    terminal: bool,
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if dry_run:
        return "dry_run"
    if judge_result and judge_result.status == "success":
        return "complete"
    if run_error or (judge_result and judge_result.status != "success"):
        return "failed"
    if terminal:
        return "complete"
    return "planned"


def _learning_status(dry_run: bool, terminal: bool) -> str:
    if dry_run:
        return "dry_run"
    return "complete" if terminal else "planned"


def _judge_artifacts(judge_result: Optional[ProviderRunResult], final_output_path: Optional[Path]) -> List[str]:
    artifacts: List[str] = []
    if judge_result is not None:
        artifacts.append("judge.prompt.md")
        artifacts.append("logs/judge.log")
    if final_output_path is not None:
        artifacts.append(Path(final_output_path).name)
    return artifacts


def _relative_or_missing(path: Optional[Path]) -> str:
    return Path(path).name if path else "not produced"


def _limitations(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> List[str]:
    if getattr(plan, "dry_run"):
        return ["- Dry-run mode verifies planning artifacts only; provider outputs are intentionally absent."]
    if run_error:
        return [f"- The run ended with an error: {run_error}"]
    if not panel_results:
        return ["- Provider execution has not produced panelist outputs yet."]
    if not any(result.status == "success" for result in panel_results):
        return ["- No panelist completed successfully, so no judge synthesis was attempted."]
    if judge_result is None:
        return ["- Judge synthesis has not completed yet."]
    if judge_result.status != "success":
        return [f"- Judge synthesis ended with status `{judge_result.status}`."]
    return ["- Verification is limited to provider exit status and captured output artifacts."]


def _verification_label(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if getattr(plan, "dry_run"):
        return "dry-run"
    if run_error or (judge_result and judge_result.status != "success"):
        return "failed"
    if judge_result and judge_result.status == "success":
        return "complete"
    if panel_results:
        return "in progress"
    return "planned"


def _panelist_groups(plan: Any, panel_results: Sequence[ProviderRunResult]) -> Tuple[List[str], List[str]]:
    considered: List[str] = []
    ignored: List[str] = []
    for panelist, result in _panel_result_pairs(list(getattr(plan, "panelists")), panel_results):
        item = f"- `{getattr(panelist, 'panelist_id')}` ({getattr(panelist, 'provider')})"
        if result and result.status == "success":
            considered.append(item)
        else:
            status = "dry-run" if getattr(plan, "dry_run") and result is None else (result.status if result else "not run")
            ignored.append(f"{item}: {status}")
    return considered, ignored


def _decision_status(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if getattr(plan, "dry_run"):
        return "dry-run"
    if judge_result and judge_result.status == "success":
        return "complete"
    if judge_result:
        return "failed"
    if run_error:
        return "blocked"
    if panel_results:
        return "pending judge"
    return "planned"


def _decision_summary(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if getattr(plan, "dry_run"):
        return "Dry-run completed. The orchestrator wrote the planned prompts and contract artifacts without calling providers."
    if judge_result and judge_result.status == "success":
        return "Judge synthesis completed and wrote the final output."
    if judge_result:
        return "Judge synthesis was attempted but did not complete successfully."
    if run_error:
        return "The run did not produce a final decision because execution stopped before judge synthesis completed."
    if panel_results and not any(result.status == "success" for result in panel_results):
        return "No panelist completed successfully, so the judge was not called."
    return "The decision is pending."


def _guardrail_recommendation(
    plan: Any,
    panel_results: Sequence[ProviderRunResult],
    judge_result: Optional[ProviderRunResult],
    run_error: str,
) -> str:
    if getattr(plan, "dry_run"):
        return "Run the same task without `--dry-run` when provider evidence is needed."
    if panel_results and not any(result.status == "success" for result in panel_results):
        return "Add or run a provider availability check before live panel execution."
    if judge_result and judge_result.status != "success":
        return "Add a regression check that fails when judge output capture returns a non-success status."
    if run_error:
        return "Add a regression check for this execution stop before expanding the workflow."
    return "No new repeated failure pattern was detected."


def _list_or_none(items: Iterable[str]) -> List[str]:
    values = list(items)
    return values if values else ["- None"]
