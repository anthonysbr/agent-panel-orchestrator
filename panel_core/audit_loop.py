from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .gates import GateRunSummary, render_gate_report, run_gates, write_gate_report
from .orchestrator import AgentPanelOrchestrator, RunPlan, parse_panel_spec
from .prompts import (
    PanelResponse,
    render_audit_judge_prompt,
    render_auditor_prompt,
    render_builder_prompt,
)
from .providers import ProviderRegistry, ProviderRunResult
from .skills import SkillRegistry, render_skill_context


CLEAN_PROMISE = "CLEAN"
CLEAN_PATTERN = re.compile(r"<promise>\s*CLEAN\s*</promise>", re.IGNORECASE)


@dataclass(frozen=True)
class AuditRoundOutcome:
    round_number: int
    gate_summary: GateRunSummary
    builder_result: ProviderRunResult
    audit_results: List[ProviderRunResult]
    judge_result: Optional[ProviderRunResult]
    clean: bool
    round_status: str = "completed"


@dataclass(frozen=True)
class AuditLoopOutcome:
    plan: RunPlan
    rounds: List[AuditRoundOutcome]
    final_output_path: Optional[Path]
    stopped_reason: str


class AuditLoopOrchestrator(AgentPanelOrchestrator):
    def __init__(
        self,
        registry: ProviderRegistry,
        runner: Optional[ProviderRunner] = None,
        runs_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
        workspace: str = "project",
    ) -> None:
        super().__init__(
            registry=registry,
            runner=runner,
            runs_dir=runs_dir,
            project_root=project_root,
            workspace=workspace,
        )

    def run_audit_loop(
        self,
        task: str,
        builder: str,
        panel: str,
        judge: str,
        dry_run: bool,
        timeout_seconds: int,
        skills_spec: str = "audit-loop,code-review",
        max_panelists: Optional[int] = None,
        max_rounds: int = 3,
        retries: int = 0,
    ) -> AuditLoopOutcome:
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")

        preview = self.preview(
            task,
            panel,
            judge,
            skills_spec,
            max_panelists=max_panelists,
        )
        builder_provider = self._resolve_builder(builder, preview)
        audit_panelists = preview.panelists
        if not audit_panelists:
            raise ValueError("audit loop requires at least one audit panelist")

        run_dir = self._create_run_dir()
        plan = RunPlan(
            panel_slug=preview.panel_slug,
            judge=preview.judge,
            panelists=audit_panelists,
            skills=preview.skills,
            dry_run=dry_run,
            run_dir=str(run_dir),
        )
        selected_skills = SkillRegistry(self.project_root).resolve(skills_spec, task)
        skill_context = render_skill_context(selected_skills)

        self._write_run_plan(run_dir, plan, task, mode="audit-loop")
        (run_dir / "audit_loop.json").write_text(
            json.dumps(
                {
                    "builder": builder_provider,
                    "max_rounds": max_rounds,
                    "clean_promise": CLEAN_PROMISE,
                    "workspace": self.workspace,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if dry_run:
            round_dir = run_dir / "rounds" / "01"
            round_dir.mkdir(parents=True)
            builder_prompt = render_builder_prompt(builder_provider, task, skill_context=skill_context)
            (round_dir / "builder.prompt.md").write_text(builder_prompt, encoding="utf-8")
            for panelist in audit_panelists:
                prompt = render_auditor_prompt(panelist.provider, task, skill_context=skill_context)
                (round_dir / f"{panelist.panelist_id}.audit.prompt.md").write_text(prompt, encoding="utf-8")
            gate_summary = run_gates(self.project_root)
            write_gate_report(run_dir, round_dir, gate_summary)
            (round_dir / "gates.md").write_text(render_gate_report(gate_summary), encoding="utf-8")
            return AuditLoopOutcome(
                plan=plan,
                rounds=[],
                final_output_path=None,
                stopped_reason="dry-run",
            )

        try:
            self._ensure_available(
                [builder_provider]
                + [panelist.provider for panelist in audit_panelists]
                + [plan.judge]
            )
        except RuntimeError as exc:
            raise

        findings = ""
        rounds: List[AuditRoundOutcome] = []
        final_path: Optional[Path] = None
        stopped_reason = "max-rounds"

        for round_number in range(1, max_rounds + 1):
            round_dir = run_dir / "rounds" / f"{round_number:02d}"
            round_dir.mkdir(parents=True)
            round_task = _compose_round_task(task, findings, round_number)

            builder_prompt = render_builder_prompt(builder_provider, round_task, skill_context=skill_context)
            (round_dir / "builder.prompt.md").write_text(builder_prompt, encoding="utf-8")
            builder_result = self.runner.run(
                builder_provider,
                builder_prompt,
                round_dir / "builder.output.md",
                run_dir / "logs" / f"round-{round_number:02d}-builder.log",
                timeout_seconds,
                workspace=self.workspace,
                project_root=self.project_root,
            )

            if builder_result.status != "success":
                rounds.append(
                    AuditRoundOutcome(
                        round_number=round_number,
                        gate_summary=GateRunSummary(passed=False, results=[]),
                        builder_result=builder_result,
                        audit_results=[],
                        judge_result=None,
                        clean=False,
                        round_status="builder_failed",
                    )
                )
                findings = _merge_findings(
                    findings,
                    f"Builder failed with status {builder_result.status}: {builder_result.error}",
                )
                continue

            gate_summary = run_gates(self.project_root)
            write_gate_report(run_dir, round_dir, gate_summary)
            (round_dir / "gates.md").write_text(render_gate_report(gate_summary), encoding="utf-8")

            audit_prompts: Dict[str, str] = {}
            for panelist in audit_panelists:
                prompt = render_auditor_prompt(
                    panelist.provider,
                    round_task,
                    skill_context=skill_context,
                    gate_report=render_gate_report(gate_summary),
                    builder_output=builder_result.output,
                )
                audit_prompts[panelist.panelist_id] = prompt
                (round_dir / f"{panelist.panelist_id}.audit.prompt.md").write_text(prompt, encoding="utf-8")

            audit_results = self._run_panelists(
                audit_panelists,
                audit_prompts,
                round_dir / "audit",
                timeout_seconds,
                retries=max(0, min(retries, 2)),
            )
            successful = [
                PanelResponse(
                    panelist_id=audit_panelists[index].panelist_id,
                    provider=result.provider,
                    status=result.status,
                    output=result.output,
                    error=result.error,
                )
                for index, result in enumerate(audit_results)
                if result.status == "success"
            ]
            if not successful:
                findings = _merge_findings(findings, "All audit panelists failed in this round.")
                rounds.append(
                    AuditRoundOutcome(
                        round_number=round_number,
                        gate_summary=gate_summary,
                        builder_result=builder_result,
                        audit_results=audit_results,
                        judge_result=None,
                        clean=False,
                    )
                )
                continue

            judge_prompt = render_audit_judge_prompt(
                plan.judge,
                round_task,
                preview.panel_slug,
                successful,
                skill_context=skill_context,
                gate_summary=gate_summary,
            )
            (round_dir / "judge.prompt.md").write_text(judge_prompt, encoding="utf-8")
            judge_path = round_dir / "judge.output.md"
            judge_result = self.runner.run(
                plan.judge,
                judge_prompt,
                judge_path,
                run_dir / "logs" / f"round-{round_number:02d}-judge.log",
                timeout_seconds,
                workspace=self.workspace,
                project_root=self.project_root,
            )
            clean = gate_summary.passed and judge_result.status == "success" and _is_clean(judge_result.output)
            rounds.append(
                AuditRoundOutcome(
                    round_number=round_number,
                    gate_summary=gate_summary,
                    builder_result=builder_result,
                    audit_results=audit_results,
                    judge_result=judge_result,
                    clean=clean,
                )
            )
            if clean:
                final_path = run_dir / "final.md"
                final_path.write_text(judge_result.output, encoding="utf-8")
                stopped_reason = "clean"
                break
            findings = _merge_findings(findings, judge_result.output)

        (run_dir / "audit_summary.json").write_text(
            json.dumps(
                {
                    "stopped_reason": stopped_reason,
                    "rounds": len(rounds),
                    "clean": stopped_reason == "clean",
                    "rounds_detail": [
                        {
                            "round": item.round_number,
                            "round_status": item.round_status,
                            "builder_status": item.builder_result.status,
                            "gates_passed": item.gate_summary.passed,
                            "clean": item.clean,
                        }
                        for item in rounds
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return AuditLoopOutcome(
            plan=plan,
            rounds=rounds,
            final_output_path=final_path,
            stopped_reason=stopped_reason,
        )

    def _resolve_builder(self, builder: str, preview) -> str:
        if builder != "auto":
            self.registry.require_provider(builder)
            return builder
        if preview.panelists:
            return preview.panelists[0].provider
        providers = parse_panel_spec("auto", self.registry)
        return providers[0]


def _compose_round_task(task: str, findings: str, round_number: int) -> str:
    if round_number == 1 or not findings.strip():
        return task
    return (
        f"{task.strip()}\n\n"
        "## Prior Round Findings\n"
        "Address every item below before declaring the work complete.\n\n"
        f"{findings.strip()}"
    )


def _merge_findings(existing: str, new_text: str) -> str:
    clean = (new_text or "").strip()
    if not clean:
        return existing
    if not existing.strip():
        return clean
    return existing.rstrip() + "\n\n---\n\n" + clean


def _is_clean(judge_output: str) -> bool:
    return bool(CLEAN_PATTERN.search(judge_output or ""))
