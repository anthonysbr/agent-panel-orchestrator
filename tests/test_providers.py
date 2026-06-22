from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from panel_core.config import CommandConfig, OrchestratorConfig, ProviderConfig
from panel_core.providers import ProviderRegistry, ProviderRunner


def make_config() -> OrchestratorConfig:
    return OrchestratorConfig(
        providers={
            "codex": ProviderConfig(
                name="codex",
                display_name="Codex CLI",
                binary="codex",
                version_args=["--version"],
        mode="stdin_stdout",
        command=["codex", "-"],
            )
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


class ProviderTests(unittest.TestCase):
    @mock.patch("panel_core.providers.subprocess.run")
    @mock.patch("panel_core.providers.shutil.which")
    def test_detection_reports_version(self, which: mock.Mock, run: mock.Mock) -> None:
        which.return_value = "/bin/codex"
        run.return_value = subprocess.CompletedProcess(["/bin/codex", "--version"], 0, "codex-cli 1.2\n", "")
        registry = ProviderRegistry(make_config())

        detected = registry.detect_providers()["codex"]

        self.assertTrue(detected.available)
        self.assertEqual(detected.path, "/bin/codex")
        self.assertEqual(detected.version, "codex-cli 1.2")

    @mock.patch("panel_core.providers.shutil.which")
    def test_detection_reports_missing(self, which: mock.Mock) -> None:
        which.return_value = None
        registry = ProviderRegistry(make_config())

        detected = registry.detect_external_tools()["gemini"]

        self.assertFalse(detected.available)
        self.assertIsNone(detected.version)

    @mock.patch("panel_core.providers.subprocess.run")
    @mock.patch("panel_core.providers.shutil.which")
    def test_runner_captures_timeout(self, which: mock.Mock, run: mock.Mock) -> None:
        which.return_value = "/bin/codex"
        run.side_effect = subprocess.TimeoutExpired(["codex"], 3)
        runner = ProviderRunner(ProviderRegistry(make_config()))

        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run(
                "codex",
                "prompt",
                Path(tmp) / "out.md",
                Path(tmp) / "log.txt",
                timeout_seconds=3,
            )

        self.assertEqual(result.status, "timeout")
        self.assertIn("timed out", result.error)

    @mock.patch("panel_core.providers.subprocess.run")
    @mock.patch("panel_core.providers.shutil.which")
    def test_runner_retries_empty_output(self, which: mock.Mock, run: mock.Mock) -> None:
        which.return_value = "/bin/codex"
        run.side_effect = [
            subprocess.CompletedProcess(["codex"], 0, "", ""),
            subprocess.CompletedProcess(["codex"], 0, "answer\n", ""),
        ]
        runner = ProviderRunner(ProviderRegistry(make_config()))

        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run(
                "codex",
                "prompt",
                Path(tmp) / "out.md",
                Path(tmp) / "log.txt",
                timeout_seconds=3,
                empty_retries=1,
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
