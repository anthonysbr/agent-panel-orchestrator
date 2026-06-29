from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dataclasses import replace

from panel_core.audit_loop import AuditLoopOrchestrator
from panel_core.config import CommandConfig, OrchestratorConfig, ProviderConfig
from panel_core.gates import run_gates
from panel_core.providers import ProviderRegistry, ProviderRunResult
from panel_core.testing.fake_runner import FakeProviderRunner, apply_expected_file, success_output


FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


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


class WorkerPoolAuditLoopIntegrationTests(unittest.TestCase):
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.providers.shutil.which")
    def test_audit_loop_reaches_clean_after_builder_fix(self, which: mock.Mock, ensure: mock.Mock) -> None:
        which.return_value = "/bin/codex"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            copy_fixture("worker-pool-bug", project)
            runs_dir = root / "runs"

            self.assertFalse(run_gates(project).passed)

            fix_applied = {"done": False}
            claude_calls = {"count": 0}

            def builder_handler(
                provider: str,
                prompt: str,
                output_path: Path,
                log_path: Path,
                project_root: Path,
            ) -> ProviderRunResult:
                apply_expected_file(project_root, "worker_pool/pool.py", "pool.py")
                fix_applied["done"] = True
                return success_output("Applied worker pool fix.")

            def claude_handler(
                provider: str,
                prompt: str,
                output_path: Path,
                log_path: Path,
                project_root: Path,
            ) -> ProviderRunResult:
                claude_calls["count"] += 1
                if claude_calls["count"] == 1:
                    return success_output("Audit: no blocking issues found.")
                return success_output("Approved.\n<promise>CLEAN</promise>")

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
                task="fix the worker pool counting bug",
                builder="codex",
                panel="claude",
                judge="claude",
                dry_run=False,
                timeout_seconds=30,
                max_rounds=3,
            )

            self.assertTrue(fix_applied["done"])
            self.assertTrue(run_gates(project).passed)
            self.assertEqual(outcome.stopped_reason, "clean")
            self.assertEqual(claude_calls["count"], 2)
            self.assertTrue((Path(outcome.plan.run_dir) / "audit_summary.json").is_file())


class FixtureGateTests(unittest.TestCase):
    def test_worker_pool_fixture_starts_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_fixture("worker-pool-bug", root)
            self.assertFalse(run_gates(root).passed)

    def test_api_monolith_fixture_has_security_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_fixture("api-monolith", root)
            summary = run_gates(root)
            self.assertFalse(summary.passed)
            names = [item.name for item in summary.results]
            self.assertIn("no-raw-sql-interpolation", names)

    def test_js_python_monorepo_fixture_has_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_fixture("js-python-monorepo", root)
            self.assertFalse(run_gates(root).passed)


if __name__ == "__main__":
    unittest.main()
