from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .branding import BRAND_NAME
from .config import load_config
from .export_rules import export_rules
from .orchestrator import AgentPanelOrchestrator
from .prompts import render_panelist_prompt
from .providers import ProviderRegistry
from .skills import SkillRegistry, adopt_proposal, evaluate_skill, improve_skill, reject_proposal, render_skill_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="panel",
        description=f"{BRAND_NAME}. Run independent agent panels through Codex, Claude Code, and Cursor CLIs.",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to agents.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("detect", help="Detect provider CLI availability")

    prompt_parser = subparsers.add_parser("prompt", help="Render a provider-specific panelist prompt")
    prompt_parser.add_argument("--agent", required=True, choices=["codex", "claude", "cursor", "gemini"])
    prompt_parser.add_argument("--skills", default="auto", help="auto, none, or a comma-separated skill list")
    prompt_parser.add_argument("--task", required=True)

    run_parser = subparsers.add_parser("run", help="Run an independent agent panel")
    run_parser.add_argument("--panel", default="auto", help="auto, codex:2, or codex,claude,cursor,gemini")
    run_parser.add_argument("--judge", default="auto", help="auto, codex, claude, cursor, or gemini")
    run_parser.add_argument("--skills", default="auto", help="auto, none, or a comma-separated skill list")
    run_parser.add_argument("--dry-run", action="store_true", help="Write prompts and run plan without calling providers")
    run_parser.add_argument("--timeout", type=int, default=1800, help="Per-provider timeout in seconds")
    run_parser.add_argument("--runs-dir", type=Path, default=None, help="Directory for run artifacts")
    run_parser.add_argument("task", nargs=argparse.REMAINDER)

    skills_parser = subparsers.add_parser("skills", help="List, inspect, create, evaluate, and improve skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)
    skills_subparsers.add_parser("list", help="List available skills")
    show_parser = skills_subparsers.add_parser("show", help="Show a skill")
    show_parser.add_argument("skill_id")
    create_parser = skills_subparsers.add_parser("create", help="Create a project skill template")
    create_parser.add_argument("skill_id")
    create_parser.add_argument("--target", type=Path, default=Path("."))
    eval_parser = skills_subparsers.add_parser("eval", help="Evaluate a skill's static checks")
    eval_parser.add_argument("skill_id")
    improve_parser = skills_subparsers.add_parser("improve", help="Create a proposed skill improvement from run artifacts")
    improve_parser.add_argument("skill_id")
    improve_parser.add_argument("--from-runs", type=Path, default=Path("runs"))
    improve_parser.add_argument("--dry-run", action="store_true")
    adopt_parser = skills_subparsers.add_parser("adopt", help="Adopt a validated skill proposal into the current project")
    adopt_parser.add_argument("proposal_id")
    reject_parser = skills_subparsers.add_parser("reject", help="Reject a skill proposal")
    reject_parser.add_argument("proposal_id")

    export_parser = subparsers.add_parser("export-rules", help="Export portable instructions into another project")
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
            return _cmd_detect(registry)
        if args.command == "prompt":
            selected_skills = SkillRegistry().resolve(args.skills, args.task)
            print(render_panelist_prompt(args.agent, args.task, skill_context=render_skill_context(selected_skills)), end="")
            return 0
        if args.command == "run":
            return _cmd_run(args, registry)
        if args.command == "skills":
            return _cmd_skills(args)
        if args.command == "export-rules":
            return _cmd_export_rules(args)
    except Exception as exc:
        print(f"panel: error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _cmd_detect(registry: ProviderRegistry) -> int:
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


def _cmd_run(args: argparse.Namespace, registry: ProviderRegistry) -> int:
    task = _parse_task(args.task)
    if not task.strip():
        raise ValueError("run requires a task after --, or piped stdin")

    orchestrator = AgentPanelOrchestrator(registry=registry, runs_dir=args.runs_dir)
    outcome = orchestrator.run(
        task=task,
        panel=args.panel,
        judge=args.judge,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
        skills_spec=args.skills,
    )

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


def _cmd_export_rules(args: argparse.Namespace) -> int:
    written = export_rules(args.target, force=args.force)
    for key, path in written.items():
        print(f"{key}: {path}")
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    registry = SkillRegistry()
    if args.skills_command == "list":
        for skill in registry.list_skills():
            print(f"{skill.skill_id}\t{skill.source}\t{skill.description}")
        return 0
    if args.skills_command == "show":
        skill = registry.get_skill(args.skill_id)
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
        result = evaluate_skill(registry.get_skill(args.skill_id))
        print(f"Skill: {result.skill_id}")
        print(f"Cases: {result.cases}")
        print(f"Passed: {result.passed}")
        print(f"Score: {result.score:.2f}")
        for failure in result.failures:
            print(f"Failure: {failure}")
        return 0 if result.score == 1.0 else 1
    if args.skills_command == "improve":
        proposal = improve_skill(registry, args.skill_id, args.from_runs, args.dry_run)
        print(f"Proposal: {proposal}")
        print((proposal / "metadata.json").read_text(encoding="utf-8"), end="")
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
