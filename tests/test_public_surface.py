from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from panel_core.prompts import render_judge_prompt, render_panelist_prompt


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_TERMS = [
    "Fusion" + "-Fable",
    "fusion" + "-fable",
    "duola" + "hypercho",
    "Claude " + "Fable",
    "Opus " + "4.8",
    "GPT-" + "5.5",
    "vendor" + "ed",
    "up" + "stream",
    "white" + "-label",
    "white " + "label",
    "ai " + "generated",
    "next" + "levelbuilder",
    "ui-ux-pro" + "-max",
    "awesome" + "-skills",
    "academic-research" + "-skills",
    "Skill" + "Opt",
]


class PublicSurfaceTests(unittest.TestCase):
    def test_public_surfaces_do_not_expose_source_identity(self) -> None:
        surfaces = {
            "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
            "BRAND.md": (ROOT / "BRAND.md").read_text(encoding="utf-8"),
            "panel --help": subprocess.run(
                [str(ROOT / "panel"), "--help"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout,
            "panel prompt": render_panelist_prompt("codex", "test"),
            "judge prompt": render_judge_prompt("codex", "test", "codex,codex", []),
            "panel skills list": subprocess.run(
                [str(ROOT / "panel"), "skills", "list"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout,
            "panel skills show": subprocess.run(
                [str(ROOT / "panel"), "skills", "show", "design"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout,
            "panel prompt with skill": subprocess.run(
                [str(ROOT / "panel"), "prompt", "--agent", "codex", "--skills", "design", "--task", "review this UI"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout,
        }

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [str(ROOT / "panel"), "export-rules", "--target", tmp],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            target = Path(tmp)
            surfaces["export AGENTS.md"] = (target / "AGENTS.md").read_text(encoding="utf-8")
            surfaces["export cursor rule"] = (
                target / ".cursor" / "rules" / "agent-panel-orchestrator.mdc"
            ).read_text(encoding="utf-8")
            surfaces["export claude skill"] = (
                target / ".claude" / "skills" / "agent-panel" / "SKILL.md"
            ).read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    str(ROOT / "panel"),
                    "run",
                    "--dry-run",
                    "--panel",
                    "codex:2",
                    "--judge",
                    "codex",
                    "--runs-dir",
                    tmp,
                    "--",
                    "test",
                ],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            run_dir = next(Path(tmp).iterdir())
            for artifact in ["task_graph.json", "verification.md", "decision.md", "learning.md"]:
                surfaces[f"run {artifact}"] = (run_dir / artifact).read_text(encoding="utf-8")

        failures = []
        for surface_name, content in surfaces.items():
            lowered = content.lower()
            for term in BLOCKED_TERMS:
                if term.lower() in lowered:
                    failures.append(f"{surface_name}: {term}")

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
