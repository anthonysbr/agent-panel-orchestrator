from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from panel_core.config import OrchestratorConfig, ProviderConfig
from panel_core.orchestrator import AgentPanelOrchestrator, choose_judge, parse_panel_spec
from panel_core.providers import Detection, ProviderRegistry, ProviderRunResult


def make_registry() -> ProviderRegistry:
    config = OrchestratorConfig(
        providers={
            name: ProviderConfig(
                name=name,
                display_name=name,
                binary=name,
                version_args=[],
                mode="stdin_stdout",
                command=[name],
            )
            for name in ["codex", "claude", "cursor"]
        },
        external_tools={},
    )
    return ProviderRegistry(config)


def available_provider_detection(name: str) -> Detection:
    return Detection(
        name=name,
        display_name=name,
        binary=name,
        available=True,
        path=f"/usr/bin/{name}",
        version="test",
        kind="provider",
    )


class FakeRunner:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = list(statuses)
        self.calls: list[tuple[str, Path]] = []

    def run(
        self,
        provider_name: str,
        prompt: str,
        output_path: Path,
        log_path: Path,
        timeout_seconds: int,
    ) -> ProviderRunResult:
        del prompt, timeout_seconds
        self.calls.append((provider_name, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("test log", encoding="utf-8")
        status = self.statuses.pop(0)
        output = "final answer" if output_path.name == "final.md" else f"{output_path.stem} answer"
        if status == "success":
            output_path.write_text(output, encoding="utf-8")
            return ProviderRunResult(provider_name, status, output, 0, [provider_name])
        return ProviderRunResult(provider_name, status, "", 1, [provider_name], error=f"{status} error")


class OrchestratorTests(unittest.TestCase):
    def test_parse_panel_with_counts(self) -> None:
        registry = make_registry()
        self.assertEqual(parse_panel_spec("codex:2", registry), ["codex", "codex"])
        self.assertEqual(parse_panel_spec("codex,claude,cursor", registry), ["codex", "claude", "cursor"])

    def test_auto_panel_duplicates_single_available_provider(self) -> None:
        registry = make_registry()
        with mock.patch.object(registry, "available_provider_names", return_value=["codex"]):
            self.assertEqual(parse_panel_spec("auto", registry), ["codex", "codex"])
            self.assertEqual(choose_judge("auto", registry), "codex")

    def test_dry_run_writes_plan_and_prompts_without_runner_calls(self) -> None:
        registry = make_registry()
        runner = mock.Mock()
        with mock.patch.object(registry, "available_provider_names", return_value=["codex"]):
            with tempfile.TemporaryDirectory() as tmp:
                outcome = AgentPanelOrchestrator(registry, runner=runner, runs_dir=Path(tmp)).run(
                    task="test",
                    panel="codex:2",
                    judge="codex",
                    dry_run=True,
                    timeout_seconds=10,
                )
                run_dir = Path(outcome.plan.run_dir)
                plan = json.loads((run_dir / "run_plan.json").read_text(encoding="utf-8"))
                graph = json.loads((run_dir / "task_graph.json").read_text(encoding="utf-8"))
                prompt_one_exists = (run_dir / "panelists" / "codex-1.prompt.md").exists()
                prompt_two_exists = (run_dir / "panelists" / "codex-2.prompt.md").exists()
                contract_files_exist = all(
                    (run_dir / name).exists()
                    for name in ["task_graph.json", "verification.md", "decision.md", "learning.md"]
                )

        runner.run.assert_not_called()
        self.assertEqual(plan["panel_slug"], "codex,codex")
        self.assertEqual(plan["judge"], "codex")
        self.assertEqual(graph["schema_version"], 1)
        self.assertEqual(graph["goal"], "test")
        self.assertEqual(
            {"intake", "panelist:codex-1", "panelist:codex-2", "judge", "verification", "learning"},
            {node["id"] for node in graph["nodes"]},
        )
        self.assertTrue(prompt_one_exists)
        self.assertTrue(prompt_two_exists)
        self.assertTrue(contract_files_exist)

    def test_live_run_writes_final_contract_artifacts(self) -> None:
        registry = make_registry()
        runner = FakeRunner(["success", "success", "success"])
        with mock.patch.object(registry, "detect_providers", return_value={"codex": available_provider_detection("codex")}):
            with tempfile.TemporaryDirectory() as tmp:
                outcome = AgentPanelOrchestrator(registry, runner=runner, runs_dir=Path(tmp)).run(
                    task="test",
                    panel="codex:2",
                    judge="codex",
                    dry_run=False,
                    timeout_seconds=10,
                )
                run_dir = Path(outcome.plan.run_dir)
                graph = json.loads((run_dir / "task_graph.json").read_text(encoding="utf-8"))
                verification = (run_dir / "verification.md").read_text(encoding="utf-8")
                decision = (run_dir / "decision.md").read_text(encoding="utf-8")
                learning = (run_dir / "learning.md").read_text(encoding="utf-8")

        self.assertEqual(3, len(runner.calls))
        self.assertEqual("success", graph["summary"]["judge_status"])
        self.assertEqual(2, graph["summary"]["panelists_successful"])
        self.assertTrue(graph["summary"]["final_output"].endswith("final.md"))
        self.assertIn("Status: complete", verification)
        self.assertIn("Decision status: complete", decision)
        self.assertIn("No new repeated failure pattern was detected.", learning)

    def test_all_panelists_failed_leaves_contract_before_error(self) -> None:
        registry = make_registry()
        runner = FakeRunner(["failed", "failed"])
        with mock.patch.object(registry, "detect_providers", return_value={"codex": available_provider_detection("codex")}):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, "all panelists failed"):
                    AgentPanelOrchestrator(registry, runner=runner, runs_dir=Path(tmp)).run(
                        task="test",
                        panel="codex:2",
                        judge="codex",
                        dry_run=False,
                        timeout_seconds=10,
                    )
                run_dirs = list(Path(tmp).iterdir())
                self.assertEqual(1, len(run_dirs))
                run_dir = run_dirs[0]
                graph = json.loads((run_dir / "task_graph.json").read_text(encoding="utf-8"))
                verification = (run_dir / "verification.md").read_text(encoding="utf-8")
                decision = (run_dir / "decision.md").read_text(encoding="utf-8")
                learning = (run_dir / "learning.md").read_text(encoding="utf-8")

        self.assertEqual("blocked", graph["summary"]["judge_status"])
        self.assertIn("all panelists failed", graph["summary"]["run_error"])
        self.assertIn("Status: failed", verification)
        self.assertIn("Decision status: blocked", decision)
        self.assertIn("Non-success panelist results: 2.", learning)

    def test_judge_failure_leaves_contract_before_error(self) -> None:
        registry = make_registry()
        runner = FakeRunner(["success", "success", "failed"])
        with mock.patch.object(registry, "detect_providers", return_value={"codex": available_provider_detection("codex")}):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, "judge failed"):
                    AgentPanelOrchestrator(registry, runner=runner, runs_dir=Path(tmp)).run(
                        task="test",
                        panel="codex:2",
                        judge="codex",
                        dry_run=False,
                        timeout_seconds=10,
                    )
                run_dir = next(Path(tmp).iterdir())
                graph = json.loads((run_dir / "task_graph.json").read_text(encoding="utf-8"))
                decision = (run_dir / "decision.md").read_text(encoding="utf-8")
                learning = (run_dir / "learning.md").read_text(encoding="utf-8")

        judge_node = next(node for node in graph["nodes"] if node["id"] == "judge")
        self.assertEqual("failed", judge_node["status"])
        self.assertIn("Decision status: failed", decision)
        self.assertIn("Judge result was `failed`.", learning)


if __name__ == "__main__":
    unittest.main()
