from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dataclasses import replace

from panel_core.audit_loop import AuditLoopOrchestrator, _is_clean
from panel_core.config import CommandConfig, OrchestratorConfig, ProviderConfig
from panel_core.providers import ProviderRegistry, ProviderRunResult, ProviderRunner


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
        external_tools={
            "gemini": CommandConfig(
                name="gemini",
                display_name="Gemini CLI",
                binary="gemini",
                version_args=["--version"],
            )
        },
    )


class AuditLoopTests(unittest.TestCase):
    def test_is_clean_requires_promise(self) -> None:
        self.assertTrue(_is_clean("All good.\n<promise>CLEAN</promise>"))
        self.assertFalse(_is_clean("All good."))

    @mock.patch("panel_core.audit_loop.run_gates")
    @mock.patch.object(ProviderRunner, "run")
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._ensure_available")
    @mock.patch("panel_core.audit_loop.AuditLoopOrchestrator._run_panelists")
    @mock.patch("panel_core.providers.shutil.which")
    def test_dry_run_writes_round_artifacts(
        self,
        which: mock.Mock,
        run_panelists: mock.Mock,
        ensure: mock.Mock,
        runner_run: mock.Mock,
        run_gates: mock.Mock,
    ) -> None:
        which.return_value = "/bin/codex"
        run_gates.return_value = mock.Mock(passed=True, results=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loop = AuditLoopOrchestrator(
                registry=ProviderRegistry(make_config()),
                runs_dir=root / "runs",
                project_root=root,
            )
            outcome = loop.run_audit_loop(
                task="fix the bug",
                builder="codex",
                panel="codex:2",
                judge="codex",
                dry_run=True,
                timeout_seconds=30,
            )
            self.assertEqual(outcome.stopped_reason, "dry-run")
            round_dir = Path(outcome.plan.run_dir) / "rounds" / "01"
            self.assertTrue((round_dir / "builder.prompt.md").exists())
            runner_run.assert_not_called()
            run_panelists.assert_not_called()


if __name__ == "__main__":
    unittest.main()
