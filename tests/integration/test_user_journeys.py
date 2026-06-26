from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from dataclasses import replace

from panel_core.audit_loop import AuditLoopOrchestrator
from panel_core.cli import main
from panel_core.config import CommandConfig, OrchestratorConfig, ProviderConfig
from panel_core.gates import run_gates
from panel_core.orchestrator import AgentPanelOrchestrator
from panel_core.providers import ProviderRegistry, ProviderRunResult
from panel_core.runs import load_run, list_runs
from panel_core.testing.fake_runner import FakeProviderRunner, apply_expected_file, success_output


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
PANEL = str(ROOT / "panel")


def make_config() -> OrchestratorConfig:
    provider = ProviderConfig(
        name="codex",
        display_name="Codex CLI",
        binary="codex",
        version_args=["--version"],
        mode="stdin_stdout",
        command=["codex", "-"],
    )
    return OrchestratorConfig(
        providers={
            "codex": provider,
            "claude": replace(provider, name="claude", display_name="Claude"),
        },
        external_tools={},
    )


def copy_fixture(name: str, dest: Path) -> None:
    shutil.copytree(FIXTURES_ROOT / name, dest, dirs_exist_ok=True)


def audit_handlers_for_fixture(
    project_root: Path,
    *,
    relative_target: str,
    expected_name: str,
    apply_on_builder_call: int = 1,
) -> tuple[FakeProviderRunner, dict[str, int]]:
    """Build fake runner: builder applies fix on Nth call; claude alternates audit/judge."""
    stats = {"builder": 0, "claude": 0}

    def builder_handler(provider, prompt, output_path, log_path, root):
        stats["builder"] += 1
        if stats["builder"] >= apply_on_builder_call:
            apply_expected_file(root, relative_target, expected_name)
            return success_output(f"Applied fix on builder call {stats['builder']}.")
        return success_output("Investigated; no code change yet.")

    def claude_handler(provider, prompt, output_path, log_path, root):
        stats["claude"] += 1
        # Odd calls = audit panelist, even = judge
        if stats["claude"] % 2 == 1:
            return success_output("Audit: findings documented.")
        if stats["builder"] >= apply_on_builder_call and run_gates(root).passed:
            output_path.write_text("Approved.\n<promise>CLEAN</promise>\n", encoding="utf-8")
            return success_output("Approved.\n<promise>CLEAN</promise>")
        return success_output("More work required before ship.")

    registry = ProviderRegistry(make_config())
    runner = FakeProviderRunner(
        registry,
        handlers={"codex": builder_handler, "claude": claude_handler},
        project_root=project_root,
        workspace="project",
    )
    return runner, stats


class MultiRoundAuditLoopTests(unittest.TestCase):
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_two_rounds_builder_fixes_on_second_attempt(self, which: mock.Mock, ensure: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            copy_fixture("worker-pool-bug", project)
            runs_dir = Path(tmp) / "runs"

            runner, stats = audit_handlers_for_fixture(
                project,
                relative_target="worker_pool/pool.py",
                expected_name="pool.py",
                apply_on_builder_call=2,
            )
            loop = AuditLoopOrchestrator(
                registry=runner.registry,
                runner=runner,
                runs_dir=runs_dir,
                project_root=project,
                workspace="project",
            )
            outcome = loop.run_audit_loop(
                task="fix worker pool count bug",
                builder="codex",
                panel="claude",
                judge="claude",
                dry_run=False,
                timeout_seconds=30,
                max_rounds=3,
            )

            self.assertEqual(outcome.stopped_reason, "clean")
            self.assertEqual(stats["builder"], 2)
            self.assertGreaterEqual(len(outcome.rounds), 2)
            self.assertFalse(outcome.rounds[0].clean)
            self.assertTrue(outcome.rounds[-1].clean)
            self.assertTrue(run_gates(project).passed)

    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_gates_pass_but_judge_without_clean_continues(self, which: mock.Mock, ensure: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            copy_fixture("worker-pool-bug", project)
            runs_dir = Path(tmp) / "runs"
            judge_calls = {"count": 0}

            def builder_handler(provider, prompt, output_path, log_path, root):
                apply_expected_file(root, "worker_pool/pool.py", "pool.py")
                return success_output("Fixed.")

            def claude_handler(provider, prompt, output_path, log_path, root):
                judge_calls["count"] += 1
                if judge_calls["count"] % 2 == 1:
                    return success_output("Audit ok.")
                if judge_calls["count"] == 2:
                    return success_output("Almost there but no promise tag.")
                return success_output("Now clean.\n<promise>CLEAN</promise>")

            registry = ProviderRegistry(make_config())
            runner = FakeProviderRunner(
                registry,
                handlers={"codex": builder_handler, "claude": claude_handler},
                project_root=project,
                workspace="project",
            )
            loop = AuditLoopOrchestrator(
                registry=registry,
                runner=runner,
                runs_dir=runs_dir,
                project_root=project,
                workspace="project",
            )
            outcome = loop.run_audit_loop(
                task="fix bug",
                builder="codex",
                panel="claude",
                judge="claude",
                dry_run=False,
                timeout_seconds=30,
                max_rounds=3,
            )

            self.assertEqual(outcome.stopped_reason, "clean")
            self.assertEqual(len(outcome.rounds), 2)
            self.assertFalse(outcome.rounds[0].clean)
            self.assertTrue(outcome.rounds[1].clean)


class AllFixturesAuditLoopTests(unittest.TestCase):
    FIXTURE_FIXES = [
        ("worker-pool-bug", "worker_pool/pool.py", "pool.py"),
        ("api-monolith", "app/handlers.py", "handlers.py"),
        ("js-python-monorepo", "python/pyproject.toml", "pyproject.toml"),
    ]

    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_each_fixture_reaches_clean_in_one_round(self, which: mock.Mock, ensure: mock.Mock) -> None:
        for fixture_name, relative_target, expected_name in self.FIXTURE_FIXES:
            with self.subTest(fixture=fixture_name):
                with tempfile.TemporaryDirectory() as tmp:
                    project = Path(tmp) / "project"
                    copy_fixture(fixture_name, project)
                    self.assertFalse(run_gates(project).passed, fixture_name)

                    runner, _ = audit_handlers_for_fixture(
                        project,
                        relative_target=relative_target,
                        expected_name=expected_name,
                        apply_on_builder_call=1,
                    )
                    loop = AuditLoopOrchestrator(
                        registry=runner.registry,
                        runner=runner,
                        runs_dir=Path(tmp) / "runs",
                        project_root=project,
                        workspace="project",
                    )
                    outcome = loop.run_audit_loop(
                        task=f"fix the known issue in {fixture_name}",
                        builder="codex",
                        panel="claude",
                        judge="claude",
                        dry_run=False,
                        timeout_seconds=30,
                        max_rounds=2,
                    )
                    self.assertEqual("clean", outcome.stopped_reason, fixture_name)
                    self.assertTrue(run_gates(project).passed, fixture_name)


class RunsInspectionAfterAuditTests(unittest.TestCase):
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_runs_show_surfaces_audit_rounds(self, which: mock.Mock, ensure: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            copy_fixture("worker-pool-bug", project)
            runs_dir = Path(tmp) / "runs"
            runner, _ = audit_handlers_for_fixture(
                project,
                relative_target="worker_pool/pool.py",
                expected_name="pool.py",
            )
            loop = AuditLoopOrchestrator(
                registry=runner.registry,
                runner=runner,
                runs_dir=runs_dir,
                project_root=project,
                workspace="project",
            )
            outcome = loop.run_audit_loop(
                task="fix",
                builder="codex",
                panel="claude",
                judge="claude",
                dry_run=False,
                timeout_seconds=30,
                max_rounds=2,
            )
            summaries = list_runs(runs_dir)
            self.assertEqual(1, len(summaries))
            self.assertEqual("audit-loop", summaries[0].mode)
            self.assertEqual("clean", summaries[0].status)

            detail = load_run(runs_dir, summaries[0].run_id)
            self.assertEqual("clean", detail.stopped_reason)
            self.assertTrue(detail.audit_rounds)
            self.assertTrue(detail.audit_rounds[-1].clean)


class CliUserJourneyTests(unittest.TestCase):
    def test_cancelled_run_returns_130(self) -> None:
        buffer = StringIO()
        with mock.patch("sys.stdout", buffer):
            with mock.patch("panel_core.cli._confirm_live_run", return_value=False):
                with mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex"):
                    code = main(["run", "--panel", "codex", "--judge", "codex", "--", "hello"])
        self.assertEqual(130, code)
        self.assertIn("Cancelled.", buffer.getvalue())

    def test_audit_loop_ci_json_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex"):
                with mock.patch(
                    "panel_core.audit_loop.AuditLoopOrchestrator.run_audit_loop",
                ) as run_loop:
                    from panel_core.audit_loop import AuditLoopOutcome
                    from panel_core.orchestrator import RunPlan

                    plan = RunPlan("codex", "codex", [], [], False, str(Path(tmp) / "run"))
                    run_loop.return_value = AuditLoopOutcome(plan, [], None, "max-rounds")

                    buffer = StringIO()
                    with mock.patch("sys.stdout", buffer):
                        code = main(
                            [
                                "run",
                                "--audit-loop",
                                "--ci",
                                "--json",
                                "--yes",
                                "--runs-dir",
                                tmp,
                                "--",
                                "task",
                            ]
                        )
                    self.assertEqual(1, code)
                    payload = json.loads(buffer.getvalue())
                    self.assertEqual("max-rounds", payload["stopped_reason"])

    def test_doctor_from_fixture_reports_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy_fixture("worker-pool-bug", Path(tmp))
            buffer = StringIO()
            with mock.patch("sys.stdout", buffer):
                with mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex"):
                    with mock.patch("os.getcwd", return_value=tmp):
                        code = main(["doctor"])
            self.assertIn(code, (0, 1))
            self.assertIn("Gates:", buffer.getvalue())


class SubprocessPanelTests(unittest.TestCase):
    FIXTURES = ["worker-pool-bug", "api-monolith", "js-python-monorepo"]

    def _run_panel(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, PANEL, *args],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_panel_doctor_in_repo_root(self) -> None:
        result = subprocess.run(
            [sys.executable, PANEL, "doctor", "--json"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("python", payload)
        self.assertIn("gates", payload)

    def test_audit_loop_dry_run_from_each_fixture(self) -> None:
        for fixture in self.FIXTURES:
            with self.subTest(fixture=fixture):
                fixture_dir = FIXTURES_ROOT / fixture
                with tempfile.TemporaryDirectory() as tmp:
                    result = self._run_panel(
                        fixture_dir,
                        "run",
                        "--audit-loop",
                        "--dry-run",
                        "--yes",
                        "--runs-dir",
                        tmp,
                        "--builder",
                        "codex",
                        "--panel",
                        "codex",
                        "--judge",
                        "codex",
                        "--max-rounds",
                        "1",
                        "--",
                        "fix the known issue",
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("dry-run", result.stdout.lower())
                    run_dirs = list(Path(tmp).iterdir())
                    self.assertEqual(1, len(run_dirs))
                    round_dir = run_dirs[0] / "rounds" / "01"
                    self.assertTrue((round_dir / "builder.prompt.md").is_file())
                    self.assertTrue((round_dir / "gates.json").is_file())

    def test_standard_run_dry_run_produces_contract_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    PANEL,
                    "run",
                    "--dry-run",
                    "--yes",
                    "--panel",
                    "codex:2",
                    "--judge",
                    "codex",
                    "--runs-dir",
                    tmp,
                    "--",
                    "review API",
                ],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            run_dir = next(Path(tmp).iterdir())
            for name in ["run_plan.json", "task_graph.json", "verification.md", "decision.md"]:
                self.assertTrue((run_dir / name).is_file(), name)

    def test_skills_eval_all_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, PANEL, "skills", "eval", "--all"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_editable_install_smoke_in_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pip = venv_dir / "bin" / "pip"
            python = venv_dir / "bin" / "python"
            install = subprocess.run(
                [str(pip), "install", "-e", str(ROOT), "--quiet"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
            self.assertEqual(0, install.returncode, install.stderr)
            smoke = subprocess.run(
                [str(python), "-m", "panel_core.cli", "skills", "list"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(0, smoke.returncode, smoke.stderr)
            self.assertIn("design", smoke.stdout)


class MaxRoundsWithoutFixTests(unittest.TestCase):
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_never_clean_exhausts_max_rounds(self, which: mock.Mock, ensure: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            copy_fixture("worker-pool-bug", project)
            runs_dir = Path(tmp) / "runs"

            def builder_handler(provider, prompt, output_path, log_path, root):
                return success_output("No changes.")

            def claude_handler(provider, prompt, output_path, log_path, root):
                return success_output("Still broken.")

            registry = ProviderRegistry(make_config())
            runner = FakeProviderRunner(
                registry,
                handlers={"codex": builder_handler, "claude": claude_handler},
                project_root=project,
                workspace="project",
            )
            loop = AuditLoopOrchestrator(
                registry=registry,
                runner=runner,
                runs_dir=runs_dir,
                project_root=project,
                workspace="project",
            )
            outcome = loop.run_audit_loop(
                task="fix",
                builder="codex",
                panel="claude",
                judge="claude",
                dry_run=False,
                timeout_seconds=30,
                max_rounds=2,
            )
            self.assertEqual("max-rounds", outcome.stopped_reason)
            self.assertFalse(run_gates(project).passed)
            summary = json.loads((Path(outcome.plan.run_dir) / "audit_summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["clean"])


class WorkspaceModePanelRunTests(unittest.TestCase):
    @mock.patch("panel_core.providers.shutil.which", return_value="/bin/codex")
    def test_project_workspace_passes_cwd_to_provider(self, which: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            copy_fixture("api-monolith", project)
            runs_dir = Path(tmp) / "runs"
            seen_cwd: list[str] = []

            def capture_handler(provider, prompt, output_path, log_path, root):
                seen_cwd.append(str(root.resolve()))
                output_path.write_text("Review complete.", encoding="utf-8")
                return success_output("Review complete.")

            registry = ProviderRegistry(make_config())
            runner = FakeProviderRunner(
                registry,
                handlers={"codex": capture_handler},
                project_root=project,
                workspace="project",
            )
            orchestrator = AgentPanelOrchestrator(
                registry=registry,
                runner=runner,
                runs_dir=runs_dir,
                project_root=project,
                workspace="project",
            )
            with mock.patch.object(orchestrator, "_ensure_available"):
                outcome = orchestrator.run(
                    task="review security of handlers",
                    panel="codex",
                    judge="codex",
                    dry_run=False,
                    timeout_seconds=30,
                )
            self.assertIsNotNone(outcome.final_output_path)
            self.assertTrue(all(Path(path).resolve() == project.resolve() for path in seen_cwd))


if __name__ == "__main__":
    unittest.main()
