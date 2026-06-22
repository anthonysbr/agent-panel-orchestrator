from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from panel_core.skills import (
    SkillRegistry,
    adopt_proposal,
    evaluate_skill,
    improve_skill,
    reject_proposal,
    render_skill_context,
)


class SkillTests(unittest.TestCase):
    def test_loads_builtin_skills_and_auto_selects(self) -> None:
        registry = SkillRegistry(project_root=Path("/tmp/nonexistent-panel-project"))
        skill_ids = {skill.skill_id for skill in registry.list_skills()}

        self.assertIn("design", skill_ids)
        self.assertIn("code-review", skill_ids)
        selected = [skill.skill_id for skill in registry.resolve("auto", "review this UI layout")]
        self.assertEqual("design", selected[0])

    def test_project_skill_overrides_builtin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = root / ".panel" / "skills" / "design"
            skill_root.mkdir(parents=True)
            (skill_root / "skill.json").write_text(
                json.dumps(
                    {
                        "id": "design",
                        "name": "Project Design",
                        "version": "9.0.0",
                        "description": "Project-specific design checks.",
                        "triggers": ["project design"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (skill_root / "instructions.md").write_text("# Project Design\n", encoding="utf-8")

            skill = SkillRegistry(project_root=root).get_skill("design")

        self.assertEqual("Project Design", skill.name)
        self.assertEqual("project", skill.source)

    def test_eval_and_context_are_stable(self) -> None:
        registry = SkillRegistry(project_root=Path("/tmp/nonexistent-panel-project"))
        skill = registry.get_skill("security")
        result = evaluate_skill(skill)
        context = render_skill_context([skill])

        self.assertEqual(1.0, result.score)
        self.assertIn("Security Skill", context)
        self.assertIn("Trust boundaries", context)

    def test_improve_creates_validated_proposal_and_adopt_writes_project_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            run = runs / "20260615T120000Z"
            run.mkdir(parents=True)
            (run / "learning.md").write_text(
                "# Learning\n\n## Guardrail Recommendation\nAdd a pre-merge checklist for risky migrations.\n",
                encoding="utf-8",
            )
            registry = SkillRegistry(project_root=root)

            proposal = improve_skill(registry, "code-review", runs, dry_run=True)
            metadata = json.loads((proposal / "metadata.json").read_text(encoding="utf-8"))
            adopted = adopt_proposal(registry, str(proposal))

            adopted_text = (adopted / "instructions.md").read_text(encoding="utf-8")

        self.assertEqual("validated", metadata["status"])
        self.assertIn("Run-Learned Guidance", adopted_text)
        self.assertIn("risky migrations", adopted_text)

    def test_adopt_rejects_untested_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = SkillRegistry(project_root=root)
            proposal = improve_skill(registry, "design", root / "missing-runs", dry_run=True)

            with self.assertRaisesRegex(ValueError, "validated"):
                adopt_proposal(registry, str(proposal))
            rejected = reject_proposal(registry, str(proposal))
            metadata = json.loads((rejected / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual("rejected", metadata["status"])

    def test_eval_supports_must_not_include(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".panel" / "skills" / "lint"
            root.mkdir(parents=True)
            (root / "skill.json").write_text(
                json.dumps(
                    {
                        "id": "lint",
                        "name": "Lint",
                        "version": "1.0.0",
                        "description": "Lint checks",
                        "triggers": ["lint"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "instructions.md").write_text("# Lint\n\nUse eslint.\n", encoding="utf-8")
            (root / "evals").mkdir()
            (root / "evals" / "basic.jsonl").write_text(
                json.dumps({"id": "basic", "must_include": ["eslint"], "must_not_include": ["todo"]})
                + "\n",
                encoding="utf-8",
            )
            skill = SkillRegistry(project_root=Path(tmp)).get_skill("lint")
            result = evaluate_skill(skill)
            self.assertEqual(1.0, result.score)

    def test_read_proposal_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = SkillRegistry(project_root=root)
            proposal = improve_skill(registry, "design", root / "missing-runs", dry_run=True)
            from panel_core.skills import read_proposal_diff

            diff = read_proposal_diff(registry, str(proposal))
            self.assertTrue(diff.endswith("\n") or diff == "")


if __name__ == "__main__":
    unittest.main()
