from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from panel_core.config import OrchestratorConfig, ProviderConfig
from panel_core.orchestrator import AgentPanelOrchestrator
from panel_core.providers import ProviderRegistry
from panel_core.runs import list_runs, load_run


def make_registry() -> ProviderRegistry:
    config = OrchestratorConfig(
        providers={
            "codex": ProviderConfig(
                name="codex",
                display_name="codex",
                binary="codex",
                version_args=[],
                mode="stdin_stdout",
                command=["codex"],
            )
        },
        external_tools={},
    )
    return ProviderRegistry(config)


class RunsTests(unittest.TestCase):
    def test_list_and_show_run(self) -> None:
        registry = make_registry()
        with mock.patch.object(registry, "available_provider_names", return_value=["codex"]):
            with tempfile.TemporaryDirectory() as tmp:
                AgentPanelOrchestrator(registry, runs_dir=Path(tmp)).run(
                    task="test",
                    panel="codex:2",
                    judge="codex",
                    dry_run=True,
                    timeout_seconds=10,
                )
                runs_dir = Path(tmp)
                summaries = list_runs(runs_dir)

                self.assertEqual(1, len(summaries))
                detail = load_run(runs_dir, summaries[0].run_id)

                self.assertEqual("codex,codex", detail.summary.panel_slug)
                self.assertTrue(detail.summary.dry_run)
                self.assertTrue(detail.artifacts["run_plan"])


if __name__ == "__main__":
    unittest.main()
