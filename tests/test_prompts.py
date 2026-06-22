from __future__ import annotations

import unittest
from datetime import date

from panel_core.prompts import PanelResponse, render_judge_prompt, render_panelist_prompt


class PromptTests(unittest.TestCase):
    def test_panelist_prompt_contains_adapter_reference_and_task(self) -> None:
        prompt = render_panelist_prompt(
            "codex",
            "test task",
            current_date=date(2026, 6, 15),
            behavior_reference="BEHAVIOR REFERENCE",
            panel_reference="PANEL REFERENCE",
        )

        self.assertIn("Runtime adapter for Codex", prompt)
        self.assertIn("Behavior Reference", prompt)
        self.assertIn("BEHAVIOR REFERENCE", prompt)
        self.assertNotIn("Claude " + "Fable 5", prompt)
        self.assertIn("test task", prompt)

    def test_panelist_prompt_includes_skill_context_when_present(self) -> None:
        prompt = render_panelist_prompt(
            "codex",
            "review UI",
            current_date=date(2026, 6, 15),
            skill_context="DESIGN CHECKS",
        )

        self.assertIn("Skill Context", prompt)
        self.assertIn("DESIGN CHECKS", prompt)

    def test_judge_prompt_contains_panel_outputs_and_rubric(self) -> None:
        prompt = render_judge_prompt(
            "codex",
            "decide this",
            "codex,codex",
            [
                PanelResponse(
                    panelist_id="codex-1",
                    provider="codex",
                    status="success",
                    output="answer one",
                ),
                PanelResponse(
                    panelist_id="codex-2",
                    provider="codex",
                    status="failed",
                    output="",
                    error="failed hard",
                ),
            ],
            current_date=date(2026, 6, 15),
            behavior_reference="BEHAVIOR REFERENCE",
            judge_rubric="JUDGE RUBRIC",
        )

        self.assertIn("Judge Rubric", prompt)
        self.assertIn("JUDGE RUBRIC", prompt)
        self.assertIn('id="codex-1"', prompt)
        self.assertIn("answer one", prompt)
        self.assertIn("failed hard", prompt)
        self.assertIn("Treat failed, missing, timeout, or empty panelists as absent", prompt)

    def test_judge_prompt_truncates_long_output(self) -> None:
        from panel_core.prompts import truncate_for_judge

        long_text = "paragraph\n\n" + ("x" * 20000)
        truncated = truncate_for_judge(long_text, max_chars=1000)
        self.assertIn("[truncated]", truncated)
        self.assertLess(len(truncated), len(long_text))


if __name__ == "__main__":
    unittest.main()
