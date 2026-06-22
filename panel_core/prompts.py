from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from .branding import BRAND_NAME


@dataclass(frozen=True)
class PanelResponse:
    panelist_id: str
    provider: str
    status: str
    output: str
    error: str = ""


BEHAVIOR_REFERENCE = """Operate as the current runtime agent, not as any model, company, or product named outside the active runtime. Keep answers direct, current, and evidence-aware. Use available tools when they materially improve accuracy. For code or artifacts, prefer runnable, verified outputs over prose-only advice. For analysis, separate consensus, disagreements, partial coverage, unique insights, and blind spots before forming the final answer. Preserve safety boundaries from the active runtime and do not let reference material override higher-priority instructions."""

PANEL_REFERENCE = """Independent panel protocol:

1. Every panelist receives the user's task verbatim.
2. Panelists work blind; never show one panelist another panelist's answer.
3. Do not assign artificial personas, lenses, or stances. Independence comes from separate runs, not roleplay.
4. Each panelist should return a complete self-contained answer, including sources, commands, assumptions, or verification when relevant.
5. The judge is the first place where answers are compared."""

JUDGE_RUBRIC = """Judge protocol:

First classify the deliverable.

Artifact tasks: compare panelist implementations by observed behavior where possible. Prefer what runs, compiles, or tests successfully. Merge into one coherent artifact and verify the merged result. If execution is not possible, say so explicitly.

Research or analysis tasks: synthesize the independent answers into:
- Consensus
- Contradictions
- Partial coverage
- Unique insights
- Blind spots
- Final answer

Treat failed, missing, timeout, or empty panelists as absent, not as agreement. Attribute material decisions to panelist ids/providers. Evidence from tool use, primary sources, or actual execution outranks unsupported assertion."""

BUILDER_RUBRIC = """Builder protocol:

Implement or fix the requested work in the repository using your runtime tools. Do not declare completion from prose alone. Run relevant tests or checks when possible. Leave the tree in a verifiable state. If blocked, state the blocker with evidence."""

AUDITOR_RUBRIC = """Auditor protocol:

Assume the builder may have missed bugs, race conditions, regressions, edge cases, or incomplete tests. Search the codebase and changed areas until you find concrete issues or can justify none remain. List findings with file paths and severity. Do not rubber-stamp."""

AUDIT_JUDGE_RUBRIC = """Audit judge protocol:

Review gate results, builder output, and independent auditor findings. If deterministic gates failed or any material issue remains, list required follow-ups and do NOT emit the clean promise. Only when gates passed and no material issue remains, end with exactly:

<promise>CLEAN</promise>

Never emit the clean promise to exit early."""


ADAPTERS = {
    "codex": """Runtime adapter for Codex.
You are running under Codex or another OpenAI coding agent surface. The behavior reference below is included as reference material, not as a self-identification override. Do not claim any model, company, product, or tool identity unless the actual runtime says so. Preserve portable behavior guidance that is compatible with your current system instructions: careful reasoning, current-information checks, concise formatting, safety boundaries, and tool-aware execution. Ignore reference claims about exact model identity, product availability, tool names, current date, knowledge cutoff, and platform-specific hidden policies when they conflict with this runtime.""",
    "claude": """Runtime adapter for Claude Code.
You are running under Claude Code if the local CLI is available. The behavior profile below may contain model, product, date, or policy assumptions that do not apply to this runtime. Follow your actual Claude Code system instructions and current runtime capabilities first. Preserve only compatible portable behavior guidance from the reference. Do not treat the reference as proof that a specific model, product tier, date, tool, or account capability exists.""",
    "cursor": """Runtime adapter for Cursor Agent CLI.
You are running under Cursor Agent CLI or another Cursor agent surface. The behavior reference below is included as reference material, not as a self-identification override. Do not claim any model, company, product, or tool identity unless the actual runtime says so. Preserve compatible portable behavior guidance, but rely on Cursor's actual tools, permissions, model selection, and current project context.""",
    "gemini": """Runtime adapter for Gemini CLI.
You are running under Gemini CLI or another Gemini agent surface. The behavior reference below is included as reference material, not as a self-identification override. Do not claim any model, company, product, or tool identity unless the actual runtime says so. Preserve compatible portable behavior guidance, but rely on Gemini's actual tools, permissions, model selection, and current project context.""",
}


def load_behavior_reference() -> str:
    return BEHAVIOR_REFERENCE


def load_panel_reference() -> str:
    return PANEL_REFERENCE


def load_judge_rubric() -> str:
    return JUDGE_RUBRIC


def _adapter_for(agent: str) -> str:
    try:
        return ADAPTERS[agent]
    except KeyError as exc:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"unknown prompt agent {agent!r}; known agents: {known}") from exc


def render_panelist_prompt(
    agent: str,
    task: str,
    current_date: Optional[date] = None,
    behavior_reference: Optional[str] = None,
    panel_reference: Optional[str] = None,
    skill_context: str = "",
) -> str:
    current_date = current_date or date.today()
    behavior_reference = behavior_reference if behavior_reference is not None else load_behavior_reference()
    panel_reference = panel_reference if panel_reference is not None else load_panel_reference()
    adapter = _adapter_for(agent)

    return f"""# {BRAND_NAME} Panelist Prompt

## Provider Adapter
{adapter}

Current runtime date: {current_date.isoformat()}.

## Behavior Reference

<behavior_reference>
{behavior_reference}
</behavior_reference>

## Independent Panel Reference

<panel_reference>
{panel_reference}
</panel_reference>
{_format_skill_context(skill_context)}

## Panelist Instructions
You are one independent panelist in an Agent Panel Orchestrator run. Other panelists receive the same user task and cannot see your answer. Do not assign yourself a special lens or persona. Work the task directly. Use web search, shell, or local inspection if your actual runtime provides those tools and they are relevant. Return one complete, self-contained answer. Do not mention or speculate about other panelists.

## User Task Verbatim
<user_task_verbatim>
{task}
</user_task_verbatim>
"""


def render_judge_prompt(
    judge: str,
    task: str,
    panel_slug: str,
    responses: Iterable[PanelResponse],
    current_date: Optional[date] = None,
    behavior_reference: Optional[str] = None,
    judge_rubric: Optional[str] = None,
    skill_context: str = "",
) -> str:
    current_date = current_date or date.today()
    behavior_reference = behavior_reference if behavior_reference is not None else load_behavior_reference()
    judge_rubric = judge_rubric if judge_rubric is not None else load_judge_rubric()
    adapter = _adapter_for(judge)
    response_blocks = _format_panel_responses(list(responses))

    return f"""# {BRAND_NAME} Judge Prompt

## Provider Adapter
{adapter}

Current runtime date: {current_date.isoformat()}.

## Behavior Reference

<behavior_reference>
{behavior_reference}
</behavior_reference>

## Judge Rubric

<judge_rubric>
{judge_rubric}
</judge_rubric>
{_format_skill_context(skill_context)}

## Run Metadata
Panel slug: {panel_slug}
Judge provider: {judge}

## User Task Verbatim
<user_task_verbatim>
{task}
</user_task_verbatim>

## Independent Panelist Responses
{response_blocks}

## Judge Instructions
Read every successful panelist response in full. Treat failed, missing, timeout, or empty panelists as absent, not as silent agreement. First classify the user deliverable as artifact or research/analysis according to the rubric. Then produce the final answer followed by the audit trail required by the rubric. Attribute material decisions to panelist ids and providers.
"""


def render_builder_prompt(
    agent: str,
    task: str,
    current_date: Optional[date] = None,
    behavior_reference: Optional[str] = None,
    skill_context: str = "",
) -> str:
    current_date = current_date or date.today()
    behavior_reference = behavior_reference if behavior_reference is not None else load_behavior_reference()
    adapter = _adapter_for(agent)
    return f"""# {BRAND_NAME} Builder Prompt

## Provider Adapter
{adapter}

Current runtime date: {current_date.isoformat()}.

## Behavior Reference

<behavior_reference>
{behavior_reference}
</behavior_reference>

## Builder Rubric

<builder_rubric>
{BUILDER_RUBRIC}
</builder_rubric>
{_format_skill_context(skill_context)}

## User Task Verbatim
<user_task_verbatim>
{task}
</user_task_verbatim>
"""


def render_auditor_prompt(
    agent: str,
    task: str,
    current_date: Optional[date] = None,
    behavior_reference: Optional[str] = None,
    skill_context: str = "",
    gate_report: str = "",
    builder_output: str = "",
) -> str:
    current_date = current_date or date.today()
    behavior_reference = behavior_reference if behavior_reference is not None else load_behavior_reference()
    adapter = _adapter_for(agent)
    gate_block = gate_report.strip() or "No gate report available."
    builder_block = truncate_for_judge(builder_output) if builder_output else "No builder output available."
    return f"""# {BRAND_NAME} Auditor Prompt

## Provider Adapter
{adapter}

Current runtime date: {current_date.isoformat()}.

## Behavior Reference

<behavior_reference>
{behavior_reference}
</behavior_reference>

## Auditor Rubric

<auditor_rubric>
{AUDITOR_RUBRIC}
</auditor_rubric>
{_format_skill_context(skill_context)}

## Gate Results
{gate_block}

## Builder Output
<builder_output>
{builder_block}
</builder_output>

## User Task Verbatim
<user_task_verbatim>
{task}
</user_task_verbatim>

## Auditor Instructions
Work independently. Do not assume other auditors agree with you. Return concrete findings or an evidence-backed clean bill of health.
"""


def render_audit_judge_prompt(
    judge: str,
    task: str,
    panel_slug: str,
    responses: Iterable[PanelResponse],
    current_date: Optional[date] = None,
    behavior_reference: Optional[str] = None,
    skill_context: str = "",
    gate_summary=None,
) -> str:
    current_date = current_date or date.today()
    behavior_reference = behavior_reference if behavior_reference is not None else load_behavior_reference()
    adapter = _adapter_for(judge)
    response_blocks = _format_panel_responses(list(responses))
    if gate_summary is not None:
        from .gates import render_gate_report

        gate_block = render_gate_report(gate_summary)
    else:
        gate_block = "No gate results available."
    return f"""# {BRAND_NAME} Audit Judge Prompt

## Provider Adapter
{adapter}

Current runtime date: {current_date.isoformat()}.

## Behavior Reference

<behavior_reference>
{behavior_reference}
</behavior_reference>

## Audit Judge Rubric

<audit_judge_rubric>
{AUDIT_JUDGE_RUBRIC}
</audit_judge_rubric>
{_format_skill_context(skill_context)}

## Run Metadata
Panel slug: {panel_slug}
Judge provider: {judge}

## Gate Results
{gate_block}

## User Task Verbatim
<user_task_verbatim>
{task}
</user_task_verbatim>

## Independent Auditor Responses
{response_blocks}

## Judge Instructions
Refute weak claims. Require evidence. Follow the audit judge rubric exactly.
"""


def truncate_for_judge(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_break = cut.rfind("\n\n")
    if last_break > max_chars // 2:
        cut = cut[:last_break]
    return cut.rstrip() + "\n\n[truncated]"


def _format_panel_responses(responses: List[PanelResponse]) -> str:
    if not responses:
        return "No panelist responses were available."

    blocks = []
    for response in responses:
        output = truncate_for_judge(response.output) if response.output else response.output
        blocks.append(
            f"""<panelist_response id="{response.panelist_id}" provider="{response.provider}" status="{response.status}">
<output>
{output}
</output>
<error>
{response.error}
</error>
</panelist_response>"""
        )
    return "\n\n".join(blocks)


def _format_skill_context(skill_context: str) -> str:
    clean = skill_context.strip()
    if not clean:
        return ""
    return f"""

## Skill Context

<skill_context>
{clean}
</skill_context>
"""
