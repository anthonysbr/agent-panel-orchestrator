from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit_loop import AuditLoopOrchestrator
from .branding import BRAND_NAME
from .config import load_config
from .doctor import run_doctor
from .export_rules import export_rules
from .orchestrator import AgentPanelOrchestrator
from .prompts import render_panelist_prompt
from .providers import ProviderRegistry
from .runs import list_runs, load_run, run_detail_to_dict, run_summary_to_dict
from .skills import (
    SkillRegistry,
    adopt_proposal,
    evaluate_all_skills,
    evaluate_skill,
    improve_skill,
    read_proposal_diff,
    reject_proposal,
    render_skill_context,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="panel",
        description=f"{BRAND_NAME}. Run independent agent panels through Codex, Claude Code, and Cursor CLIs.",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to agents.json")
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("detect", parents=[json_parent], help="Detect provider CLI availability")
    subparsers.add_parser("doctor", parents=[json_parent], help="Check Python, install source, and provider CLIs")

    prompt_parser = subparsers.add_parser("prompt", help="Render a provider-specific panelist prompt")
    prompt_parser.add_argument("--agent", required=True, choices=["codex", "claude", "cursor", "gemini"])
    prompt_parser.add_argument("--skills", default="auto", help="auto, none, or a comma-separated skill list")
    prompt_parser.add_argument("--task", required=True)

    run_parser = subparsers.add_parser("run", parents=[json_parent], help="Run an independent agent panel")
    run_parser.add_argument("--panel", default="auto", help="auto, codex:2, or codex,claude,cursor,gemini")
    run_parser.add_argument("--judge", default="auto", help="auto, codex, claude, cursor, or gemini")
    run_parser.add_argument("--skills", default="auto", help="auto, none, or a comma-separated skill list")
    run_parser.add_argument("--dry-run", action="store_true", help="Write prompts and run plan without calling providers")
    run_parser.add_argument("--yes", "-y", action="store_true", help="Skip live-run confirmation prompt")
    run_parser.add_argument("--timeout", type=int, default=1800, help="Per-provider timeout in seconds")
    run_parser.add_argument("--max-panelists", type=int, default=None, help="Cap panel size for auto and explicit specs")
    run_parser.add_argument("--retries", type=int, default=0, help="Retry failed panelists up to N times (max 2)")
    run_parser.add_argument("--audit-loop", action="store_true", help="Run builder → gates → audit panel → judge until clean or max rounds")
    run_parser.add_argument("--builder", default="auto", help="Builder provider for --audit-loop (auto uses first panelist provider)")
    run_parser.add_argument("--max-rounds", type=int, default=3, help="Maximum audit-loop rounds (default 3)")
    run_parser.add_argument("--runs-dir", type=Path, default=None, help="Directory for run artifacts")
    run_parser.add_argument("task", nargs=argparse.REMAINDER)

    runs_parser = subparsers.add_parser("runs", parents=[json_parent], help="Inspect previous run artifacts")
    runs_sub = runs_parser.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_sub.add_parser("list", help="List runs in the runs directory")
    runs_list.add_argument("--runs-dir", type=Path, default=Path("runs"))
    runs_show = runs_sub.add_parser("show", help="Show one run")
    runs_show.add_argument("run_id")
    runs_show.add_argument("--runs-dir", type=Path, default=Path("runs"))

    skills_parser = subparsers.add_parser("skills", parents=[json_parent], help="List, inspect, create, evaluate, and improve skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)
    skills_subparsers.add_parser("list", help="List available skills")
    show_parser = skills_subparsers.add_parser("show", help="Show a skill")
    show_parser.add_argument("skill_id")
    create_parser = skills_subparsers.add_parser("create", help="Create a project skill template")
    create_parser.add_argument("skill_id")
    create_parser.add_argument("--target", type=Path, default=Path("."))
    eval_parser = skills_subparsers.add_parser("eval", help="Evaluate a skill's static checks")
    eval_parser.add_argument("skill_id", nargs="?")
    eval_parser.add_argument("--all", action="store_true", help="Evaluate every available skill")
    improve_parser = skills_subparsers.add_parser("improve", help="Create a proposed skill improvement from run artifacts")
    improve_parser.add_argument("skill_id")
    improve_parser.add_argument("--from-runs", type=Path, default=Path("runs"))
    improve_parser.add_argument("--dry-run", action="store_true")
    diff_parser = skills_subparsers.add_parser("diff", help="Show a skill proposal diff")
    diff_parser.add_argument("proposal_id")
    adopt_parser = skills_subparsers.add_parser("adopt", help="Adopt a validated skill proposal into the current project")
    adopt_parser.add_argument("proposal_id")
    reject_parser = skills_subparsers.add_parser("reject", help="Reject a skill proposal")
    reject_parser.add_argument("proposal_id")

    export_parser = subparsers.add_parser("export-rules", parents=[json_parent], help="Export portable instructions into another project")
    export_parser.add_argument("--target", type=Path, required=True)
    export_parser.add_argument("--force", action="store_true", help="Overwrite existing exported files")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config) if args.config else load_config()
    registry = ProviderRegistry(config)

    try:
        if args.command == "detect":
            return _cmd_detect(registry, args)
        if args.command == "doctor":
            return _cmd_doctor(registry, args)
        if args.command == "prompt":
            return _cmd_prompt(args)
        if args.command == "run":
            return _cmd_run(args, registry)
        if args.command == "runs":
            return _cmd_runs(args)
        if args.command == "skills":
            return _cmd_skills(args)
        if args.command == "export-rules":
            return _cmd_export_rules(args)
    except Exception as exc:
        print(f"panel: error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _emit_json(payload: Any) -> int:
    print(json.dumps(payload, indent=2))
    return 0


def _providers_payload(registry: ProviderRegistry) -> Dict[str, Any]:
    providers = {}
    for name, detected in registry.detect_providers().items():
        providers[name] = {
            "available": detected.available,
            "path": detected.path,
            "version": detected.version,
        }
    external = {}
    for name, detected in registry.detect_external_tools().items():
        external[name] = {
            "available": detected.available,
            "path": detected.path,
            "version": detected.version,
        }
    return {"providers": providers, "external_tools": external}


def _cmd_detect(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    payload = _providers_payload(registry)
    if args.json:
        return _emit_json(payload)

    print("Providers:")
    for name, detected in registry.detect_providers().items():
        status = "available" if detected.available else "missing"
        version = f" ({detected.version})" if detected.version else ""
        path = f" at {detected.path}" if detected.path else ""
        print(f"  {name}: {status}{version}{path}")

    external = registry.detect_external_tools()
    if external:
        print("External tools:")
        for name, detected in external.items():
            status = "available" if detected.available else "missing"
            version = f" ({detected.version})" if detected.version else ""
            path = f" at {detected.path}" if detected.path else ""
            print(f"  {name}: {status}{version}{path}")
    return 0


def _cmd_doctor(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    report = run_doctor(registry)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    python = report["python"]
    print(f"Python: {python['version']} ({'ok' if python['ok'] else 'needs >=3.10'})")
    install = report["install"]
    print(f"Install: {install['source']} ({install['executable']})")
    print(f"Panel: {report['panel_version']}")
    print("Providers:")
    for item in report["providers"]["items"]:
        status = "available" if item["available"] else "missing"
        version = f" ({item['version']})" if item.get("version") else ""
        path = f" at {item['path']}" if item.get("path") else ""
        print(f"  {item['name']}: {status}{version}{path}")
    return 0 if report.get("ok") else 1


def _cmd_prompt(args: argparse.Namespace) -> int:
    selected_skills = SkillRegistry().resolve(args.skills, args.task)
    print(render_panelist_prompt(args.agent, args.task, skill_context=render_skill_context(selected_skills)), end="")
    return 0


def _confirm_live_run() -> bool:
    try:
        answer = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _cmd_run(args: argparse.Namespace, registry: ProviderRegistry) -> int:
    task = _parse_task(args.task)
    if not task.strip():
        raise ValueError("run requires a task after --, or piped stdin")

    orchestrator = AgentPanelOrchestrator(registry=registry, runs_dir=args.runs_dir)
    loop_label = "audit-loop" if args.audit_loop else "run"
    if not args.dry_run and not args.yes:
        preview = orchestrator.preview(
            task=task,
            panel=args.panel,
            judge=args.judge,
            skills_spec=args.skills if not args.audit_loop else (args.skills if args.skills != "auto" else "audit-loop,code-review"),
            max_panelists=args.max_panelists,
        )
        skills = ", ".join(preview.skills) if preview.skills else "none"
        extra = ""
        if args.audit_loop:
            extra = f"  Builder: {args.builder}  Max rounds: {args.max_rounds}"
        print(
            f"Panel: {preview.panel_slug}  Judge: {preview.judge}  Skills: {skills}  Timeout: {args.timeout}s{extra}"
        )
        if args.audit_loop:
            print(f"Mode: audit-loop ({loop_label})")
        print(f"Panelists: {len(preview.panelists)} live provider calls + 1 judge call")
        if not _confirm_live_run():
            print("Cancelled.")
            return 0

    if args.audit_loop:
        loop = AuditLoopOrchestrator(registry=registry, runs_dir=args.runs_dir)
        outcome = loop.run_audit_loop(
            task=task,
            builder=args.builder,
            panel=args.panel,
            judge=args.judge,
            dry_run=args.dry_run,
            timeout_seconds=args.timeout,
            skills_spec=args.skills if args.skills != "auto" else "audit-loop,code-review",
            max_panelists=args.max_panelists,
            max_rounds=args.max_rounds,
            retries=args.retries,
        )
        payload = {
            "run_dir": outcome.plan.run_dir,
            "panel": outcome.plan.panel_slug,
            "judge": outcome.plan.judge,
            "skills": outcome.plan.skills,
            "dry_run": outcome.plan.dry_run,
            "audit_loop": True,
            "stopped_reason": outcome.stopped_reason,
            "rounds": len(outcome.rounds),
            "final_output": str(outcome.final_output_path) if outcome.final_output_path else None,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if outcome.stopped_reason in {"clean", "dry-run"} else 1

        print(f"Run directory: {outcome.plan.run_dir}")
        print(f"Audit loop stopped: {outcome.stopped_reason}")
        print(f"Rounds completed: {len(outcome.rounds)}")
        if args.dry_run:
            print("Dry run complete. Provider CLIs were not called.")
            return 0
        if outcome.final_output_path:
            print(f"Final answer: {outcome.final_output_path}")
            print()
            print(outcome.final_output_path.read_text(encoding="utf-8"), end="")
            return 0
        return 1

    outcome = orchestrator.run(
        task=task,
        panel=args.panel,
        judge=args.judge,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
        skills_spec=args.skills,
        max_panelists=args.max_panelists,
        retries=args.retries,
    )

    payload = {
        "run_dir": outcome.plan.run_dir,
        "panel": outcome.plan.panel_slug,
        "judge": outcome.plan.judge,
        "skills": outcome.plan.skills,
        "dry_run": outcome.plan.dry_run,
        "final_output": str(outcome.final_output_path) if outcome.final_output_path else None,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Run directory: {outcome.plan.run_dir}")
    print(f"Panel: {outcome.plan.panel_slug}")
    print(f"Judge: {outcome.plan.judge}")
    print(f"Skills: {', '.join(outcome.plan.skills) if outcome.plan.skills else 'none'}")

    if args.dry_run:
        print("Dry run complete. Provider CLIs were not called.")
        return 0

    if outcome.final_output_path:
        print(f"Final answer: {outcome.final_output_path}")
        print()
        print(outcome.final_output_path.read_text(encoding="utf-8"), end="")
    return 0


def _cmd_runs(args: argparse.Namespace) -> int:
    if args.runs_command == "list":
        summaries = list_runs(args.runs_dir)
        if args.json:
            return _emit_json([run_summary_to_dict(item) for item in summaries])
        if not summaries:
            print(f"No runs in {args.runs_dir}")
            return 0
        for item in summaries:
            mode = "dry-run" if item.dry_run else "live"
            skills = ",".join(item.skills) if item.skills else "none"
            print(f"{item.run_id}\t{mode}\t{item.panel_slug}\t{item.judge}\t{skills}")
        return 0

    if args.runs_command == "show":
        detail = load_run(args.runs_dir, args.run_id)
        if args.json:
            return _emit_json(run_detail_to_dict(detail))
        summary = detail.summary
        print(f"Run: {summary.run_id}")
        print(f"Panel: {summary.panel_slug}")
        print(f"Judge: {summary.judge}")
        print(f"Skills: {', '.join(summary.skills) if summary.skills else 'none'}")
        print(f"Mode: {'dry-run' if summary.dry_run else 'live'}")
        print(f"Status: {detail.status}")
        if detail.run_error:
            print(f"Error: {detail.run_error}")
        if detail.final_output:
            print(f"Final: {detail.final_output}")
        for key, path in detail.artifacts.items():
            if path:
                print(f"{key}: {path}")
        return 0

    raise ValueError(f"unknown runs command: {args.runs_command}")


def _cmd_export_rules(args: argparse.Namespace) -> int:
    written = export_rules(args.target, force=args.force)
    if args.json:
        return _emit_json({key: str(path) for key, path in written.items()})
    for key, path in written.items():
        print(f"{key}: {path}")
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    registry = SkillRegistry()
    if args.skills_command == "list":
        skills = registry.list_skills()
        if args.json:
            payload = [
                {
                    "skill_id": skill.skill_id,
                    "source": skill.source,
                    "description": skill.description,
                }
                for skill in skills
            ]
            return _emit_json(payload)
        for skill in skills:
            print(f"{skill.skill_id}\t{skill.source}\t{skill.description}")
        return 0
    if args.skills_command == "show":
        skill = registry.get_skill(args.skill_id)
        if args.json:
            return _emit_json(
                {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "version": skill.version,
                    "source": skill.source,
                    "instructions": skill.read_instructions(),
                }
            )
        print(f"# {skill.name} ({skill.skill_id})")
        print(f"Version: {skill.version}")
        print(f"Source: {skill.source}")
        print()
        print(skill.read_instructions(), end="")
        return 0
    if args.skills_command == "create":
        path = registry.create_project_skill(args.skill_id, args.target)
        print(f"Created skill: {path}")
        return 0
    if args.skills_command == "eval":
        if args.all:
            results = evaluate_all_skills(registry)
            if args.json:
                return _emit_json(
                    [
                        {
                            "skill_id": result.skill_id,
                            "cases": result.cases,
                            "passed": result.passed,
                            "score": result.score,
                            "failures": result.failures,
                        }
                        for result in results
                    ]
                )
            failed = False
            for result in results:
                print(f"Skill: {result.skill_id}")
                print(f"Cases: {result.cases}")
                print(f"Passed: {result.passed}")
                print(f"Score: {result.score:.2f}")
                for failure in result.failures:
                    print(f"Failure: {failure}")
                    failed = True
                print()
            return 1 if failed or any(result.score != 1.0 for result in results) else 0
        if not args.skill_id:
            raise ValueError("skills eval requires a skill_id or --all")
        result = evaluate_skill(registry.get_skill(args.skill_id))
        if args.json:
            return _emit_json(
                {
                    "skill_id": result.skill_id,
                    "cases": result.cases,
                    "passed": result.passed,
                    "score": result.score,
                    "failures": result.failures,
                }
            )
        print(f"Skill: {result.skill_id}")
        print(f"Cases: {result.cases}")
        print(f"Passed: {result.passed}")
        print(f"Score: {result.score:.2f}")
        for failure in result.failures:
            print(f"Failure: {failure}")
        return 0 if result.score == 1.0 else 1
    if args.skills_command == "improve":
        proposal = improve_skill(registry, args.skill_id, args.from_runs, args.dry_run)
        if args.json:
            return _emit_json(json.loads((proposal / "metadata.json").read_text(encoding="utf-8")))
        print(f"Proposal: {proposal}")
        print((proposal / "metadata.json").read_text(encoding="utf-8"), end="")
        return 0
    if args.skills_command == "diff":
        diff = read_proposal_diff(registry, args.proposal_id)
        if args.json:
            return _emit_json({"proposal_id": args.proposal_id, "diff": diff})
        print(diff, end="")
        return 0
    if args.skills_command == "adopt":
        target = adopt_proposal(registry, args.proposal_id)
        print(f"Adopted proposal into: {target}")
        return 0
    if args.skills_command == "reject":
        proposal = reject_proposal(registry, args.proposal_id)
        print(f"Rejected proposal: {proposal}")
        return 0
    raise ValueError(f"unknown skills command: {args.skills_command}")


def _parse_task(parts: List[str]) -> str:
    clean = list(parts)
    if clean and clean[0] == "--":
        clean = clean[1:]
    if clean:
        return " ".join(clean)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
