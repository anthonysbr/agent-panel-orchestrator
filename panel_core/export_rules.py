from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .branding import BRAND_NAME, CREATOR_LABEL, CREATOR_URL
from .paths import resolve_panel_executable
from .prompts import JUDGE_RUBRIC, PANEL_REFERENCE


def render_agents_md(orchestrator_path: Path) -> str:
    return f"""# {BRAND_NAME} Instructions

Local command:

`{orchestrator_path}`

```bash
{orchestrator_path} run --skills auto --panel auto --judge auto -- "<task>"
```

Maintainer: {CREATOR_LABEL}
Site: {CREATOR_URL}
"""


def render_cursor_rule(orchestrator_path: Path) -> str:
    return f"""---
description: Use when the user asks for an agent panel, independent cross-checking, or multi-agent synthesis.
alwaysApply: false
---

# {BRAND_NAME}

When asked to run something through an agent panel or independent cross-check, use the local orchestrator:

```bash
{orchestrator_path} run --skills auto --panel auto --judge auto -- "<task>"
```
"""


def render_claude_skill(orchestrator_path: Path) -> str:
    return f"""---
name: agent-panel
description: Run a task through Agent Panel Orchestrator with independent panelists and a final judge pass.
---

# {BRAND_NAME}

Use this skill when the user asks to run something through an agent panel or independent cross-check.

Run:

```bash
{orchestrator_path} run --skills auto --panel auto --judge auto -- "$ARGUMENTS"
```
"""


def export_rules(target: Path, force: bool = False, orchestrator_path: Optional[Path] = None) -> Dict[str, Path]:
    target = target.resolve()
    orchestrator_path = (orchestrator_path or resolve_panel_executable()).resolve()

    files = {
        "agents": target / "AGENTS.md",
        "cursor": target / ".cursor" / "rules" / "agent-panel-orchestrator.mdc",
        "claude_skill": target / ".claude" / "skills" / "agent-panel" / "SKILL.md",
    }
    existing = [path for path in files.values() if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"refusing to overwrite existing file(s): {joined}; pass --force")

    files["agents"].parent.mkdir(parents=True, exist_ok=True)
    files["cursor"].parent.mkdir(parents=True, exist_ok=True)
    files["claude_skill"].parent.mkdir(parents=True, exist_ok=True)

    files["agents"].write_text(render_agents_md(orchestrator_path), encoding="utf-8")
    files["cursor"].write_text(render_cursor_rule(orchestrator_path), encoding="utf-8")
    files["claude_skill"].write_text(render_claude_skill(orchestrator_path), encoding="utf-8")

    refs_dir = target / ".claude" / "skills" / "agent-panel" / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "panel.md").write_text("# Independent Panel Protocol\n\n" + PANEL_REFERENCE + "\n", encoding="utf-8")
    (refs_dir / "judge_rubric.md").write_text("# Judge Rubric\n\n" + JUDGE_RUBRIC + "\n", encoding="utf-8")

    return files
