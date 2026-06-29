from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .prompts import PanelResponse, render_judge_prompt, render_panelist_prompt
from .providers import ProviderRegistry, ProviderRunResult, ProviderRunner
from .run_contract import write_run_contract
from .skills import SkillRegistry, render_skill_context


DEFAULT_PROVIDER_ORDER = ["claude", "codex", "cursor", "gemini"]
RETRYABLE_STATUSES = {"failed", "timeout", "empty"}


@dataclass(frozen=True)
class PanelistPlan:
    panelist_id: str
    provider: str


@dataclass(frozen=True)
class RunPlan:
    panel_slug: str
    judge: str
    panelists: List[PanelistPlan]
    skills: List[str]
    dry_run: bool
    run_dir: str


@dataclass(frozen=True)
class RunPreview:
    panel_slug: str
    judge: str
    panelists: List[PanelistPlan]
    skills: List[str]


@dataclass(frozen=True)
class RunOutcome:
    plan: RunPlan
    panel_results: List[ProviderRunResult]
    judge_result: Optional[ProviderRunResult]
    final_output_path: Optional[Path]


def parse_panel_spec(
    panel: str,
    registry: ProviderRegistry,
    max_panelists: Optional[int] = None,
) -> List[str]:
    if panel == "auto":
        available = registry.available_provider_names()
        ordered = [name for name in DEFAULT_PROVIDER_ORDER if name in available]
        ordered.extend(name for name in available if name not in ordered)
        if not ordered:
            raise ValueError("no runnable providers detected; install Codex, Claude Code, or Cursor CLI")
        if max_panelists is not None and max_panelists > 0:
            ordered = ordered[:max_panelists]
        if len(ordered) >= 2:
            return ordered
        return [ordered[0], ordered[0]]

    providers: List[str] = []
    for item in panel.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            provider, raw_count = item.split(":", 1)
            provider = provider.strip()
            try:
                count = int(raw_count)
            except ValueError as exc:
                raise ValueError(f"invalid panel count in {item!r}") from exc
            if count < 1:
                raise ValueError(f"panel count for {provider!r} must be at least 1")
            providers.extend([provider] * count)
        else:
            providers.append(item)

    if not providers:
        raise ValueError("panel spec did not name any providers")

    if max_panelists is not None and max_panelists > 0 and len(providers) > max_panelists:
        providers = providers[:max_panelists]

    known = set(registry.config.providers)
    unknown = sorted(set(providers) - known)
    if unknown:
        raise ValueError(f"unknown panel provider(s): {', '.join(unknown)}")
    return providers


def choose_judge(judge: str, registry: ProviderRegistry) -> str:
    if judge != "auto":
        registry.require_provider(judge)
        return judge

    available = set(registry.available_provider_names())
    for candidate in DEFAULT_PROVIDER_ORDER:
        if candidate in available:
            return candidate
    if available:
        return sorted(available)[0]
    raise ValueError("no judge provider detected; install Codex, Claude Code, or Cursor CLI")


def build_panelist_plan(providers: Sequence[str]) -> List[PanelistPlan]:
    counts: Dict[str, int] = {}
    plan = []
    for provider in providers:
        counts[provider] = counts.get(provider, 0) + 1
        plan.append(PanelistPlan(panelist_id=f"{provider}-{counts[provider]}", provider=provider))
    return plan


def panel_slug_from_plan(panelists: Iterable[PanelistPlan]) -> str:
    return ",".join(panelist.provider for panelist in panelists)


def preview_run(
    registry: ProviderRegistry,
    task: str,
    panel: str,
    judge: str,
    skills_spec: str,
    project_root: Optional[Path] = None,
    max_panelists: Optional[int] = None,
) -> RunPreview:
    providers = parse_panel_spec(panel, registry, max_panelists=max_panelists)
    chosen_judge = choose_judge(judge, registry)
    panelists = build_panelist_plan(providers)
    root = (project_root or Path.cwd()).resolve()
    selected_skills = SkillRegistry(root).resolve(skills_spec, task)
    return RunPreview(
        panel_slug=panel_slug_from_plan(panelists),
        judge=chosen_judge,
        panelists=panelists,
        skills=[skill.skill_id for skill in selected_skills],
    )


class AgentPanelOrchestrator:
    def __init__(
        self,
        registry: ProviderRegistry,
        runner: Optional[ProviderRunner] = None,
        runs_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
        workspace: str = "scratch",
    ) -> None:
        self.registry = registry
        self.project_root = (project_root or Path.cwd()).resolve()
        self.workspace = workspace
        self.runner = runner or ProviderRunner(registry, project_root=self.project_root, workspace=workspace)
        self.runs_dir = runs_dir or Path.cwd() / "runs"

    def preview(
        self,
        task: str,
        panel: str,
        judge: str,
        skills_spec: str = "auto",
        max_panelists: Optional[int] = None,
    ) -> RunPreview:
        return preview_run(
            self.registry,
            task,
            panel,
            judge,
            skills_spec,
            project_root=self.project_root,
            max_panelists=max_panelists,
        )

    def run(
        self,
        task: str,
        panel: str,
        judge: str,
        dry_run: bool,
        timeout_seconds: int,
        skills_spec: str = "auto",
        max_panelists: Optional[int] = None,
        retries: int = 0,
    ) -> RunOutcome:
        preview = self.preview(task, panel, judge, skills_spec, max_panelists=max_panelists)
        run_dir = self._create_run_dir()
        plan = RunPlan(
            panel_slug=preview.panel_slug,
            judge=preview.judge,
            panelists=preview.panelists,
            skills=preview.skills,
            dry_run=dry_run,
            run_dir=str(run_dir),
        )

        selected_skills = SkillRegistry(self.project_root).resolve(skills_spec, task)
        skill_context = render_skill_context(selected_skills)

        self._write_run_plan(run_dir, plan, task)
        prompt_dir = run_dir / "panelists"
        prompt_dir.mkdir(parents=True, exist_ok=True)

        panel_prompts: Dict[str, str] = {}
        for panelist in plan.panelists:
            prompt = render_panelist_prompt(panelist.provider, task, skill_context=skill_context)
            panel_prompts[panelist.panelist_id] = prompt
            (prompt_dir / f"{panelist.panelist_id}.prompt.md").write_text(prompt, encoding="utf-8")

        write_run_contract(run_dir, task, plan)
        if dry_run:
            return RunOutcome(plan=plan, panel_results=[], judge_result=None, final_output_path=None)

        try:
            self._ensure_available([panelist.provider for panelist in plan.panelists] + [plan.judge])
        except RuntimeError as exc:
            write_run_contract(run_dir, task, plan, run_error=str(exc))
            raise

        panel_results = self._run_panelists(
            plan.panelists,
            panel_prompts,
            prompt_dir,
            timeout_seconds,
            retries=max(0, min(retries, 2)),
        )
        write_run_contract(run_dir, task, plan, panel_results=panel_results)
        successful = [
            PanelResponse(
                panelist_id=plan.panelists[index].panelist_id,
                provider=result.provider,
                status=result.status,
                output=result.output,
                error=result.error,
            )
            for index, result in enumerate(panel_results)
        ]
        if not any(result.status == "success" for result in panel_results):
            message = f"all panelists failed; see {prompt_dir}"
            write_run_contract(run_dir, task, plan, panel_results=panel_results, run_error=message)
            raise RuntimeError(message)

        judge_prompt = render_judge_prompt(
            plan.judge,
            task,
            plan.panel_slug,
            successful,
            skill_context=skill_context,
        )
        judge_prompt_path = run_dir / "judge.prompt.md"
        judge_prompt_path.write_text(judge_prompt, encoding="utf-8")
        final_path = run_dir / "final.md"
        judge_result = self.runner.run(
            plan.judge,
            judge_prompt,
            final_path,
            run_dir / "logs" / "judge.log",
            timeout_seconds,
            workspace=self.workspace,
            project_root=self.project_root,
        )
        if judge_result.status != "success":
            message = f"judge failed with status {judge_result.status}: {judge_result.error}"
            write_run_contract(
                run_dir,
                task,
                plan,
                panel_results=panel_results,
                judge_result=judge_result,
                run_error=message,
            )
            raise RuntimeError(message)

        write_run_contract(
            run_dir,
            task,
            plan,
            panel_results=panel_results,
            judge_result=judge_result,
            final_output_path=final_path,
        )

        return RunOutcome(
            plan=plan,
            panel_results=panel_results,
            judge_result=judge_result,
            final_output_path=final_path,
        )

    def _create_run_dir(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.runs_dir / timestamp
        candidate = base
        counter = 1
        while candidate.exists():
            counter += 1
            candidate = self.runs_dir / f"{timestamp}-{counter}"
        candidate.mkdir(parents=True)
        return candidate

    def _write_run_plan(self, run_dir: Path, plan: RunPlan, task: str, mode: str = "run") -> None:
        (run_dir / "task.md").write_text(task, encoding="utf-8")
        payload = {
            "mode": mode,
            "panel_slug": plan.panel_slug,
            "judge": plan.judge,
            "dry_run": plan.dry_run,
            "run_dir": plan.run_dir,
            "skills": plan.skills,
            "panelists": [asdict(panelist) for panelist in plan.panelists],
        }
        (run_dir / "run_plan.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _ensure_available(self, providers: Sequence[str]) -> None:
        detections = self.registry.detect_providers()
        missing = sorted({provider for provider in providers if not detections[provider].available})
        if missing:
            raise RuntimeError(f"missing provider CLI(s): {', '.join(missing)}")

    def _run_panelist_once(
        self,
        panelist: PanelistPlan,
        prompt: str,
        panel_dir: Path,
        logs_dir: Path,
        timeout_seconds: int,
    ) -> ProviderRunResult:
        output_path = panel_dir / f"{panelist.panelist_id}.output.md"
        log_path = logs_dir / f"{panelist.panelist_id}.log"
        return self.runner.run(
            panelist.provider,
            prompt,
            output_path,
            log_path,
            timeout_seconds,
            workspace=self.workspace,
            project_root=self.project_root,
        )

    def _run_panelists(
        self,
        panelists: Sequence[PanelistPlan],
        prompts: Dict[str, str],
        panel_dir: Path,
        timeout_seconds: int,
        retries: int = 0,
    ) -> List[ProviderRunResult]:
        results_by_id: Dict[str, ProviderRunResult] = {}
        logs_dir = panel_dir.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        def execute(panelist: PanelistPlan) -> ProviderRunResult:
            result = self._run_panelist_once(
                panelist,
                prompts[panelist.panelist_id],
                panel_dir,
                logs_dir,
                timeout_seconds,
            )
            attempts = 0
            while result.status in RETRYABLE_STATUSES and attempts < retries:
                attempts += 1
                result = self._run_panelist_once(
                    panelist,
                    prompts[panelist.panelist_id],
                    panel_dir,
                    logs_dir,
                    timeout_seconds,
                )
            return result

        with ThreadPoolExecutor(max_workers=len(panelists)) as executor:
            futures = {executor.submit(execute, panelist): panelist.panelist_id for panelist in panelists}
            for future in as_completed(futures):
                panelist_id = futures[future]
                results_by_id[panelist_id] = future.result()

        return [results_by_id[panelist.panelist_id] for panelist in panelists]
