from __future__ import annotations

import json
import unittest
from unittest import mock

from panel_core.config import OrchestratorConfig, ProviderConfig
from panel_core.doctor import run_doctor
from panel_core.providers import Detection, ProviderRegistry


def make_registry(available: bool = True) -> ProviderRegistry:
    config = OrchestratorConfig(
        providers={
            "codex": ProviderConfig(
                name="codex",
                display_name="Codex",
                binary="codex",
                version_args=[],
                mode="stdin_stdout",
                command=["codex"],
            )
        },
        external_tools={},
    )
    registry = ProviderRegistry(config)
    return registry


class DoctorTests(unittest.TestCase):
    def test_run_doctor_json_shape(self) -> None:
        registry = make_registry()
        detection = Detection(
            name="codex",
            display_name="Codex",
            binary="codex",
            available=True,
            path="/usr/bin/codex",
            version="1.0",
            kind="provider",
        )
        with unittest.mock.patch.object(registry, "detect_providers", return_value={"codex": detection}):
            report = run_doctor(registry)

        self.assertIn("python", report)
        self.assertIn("install", report)
        self.assertIn("providers", report)
        self.assertIn("panel_version", report)
        self.assertTrue(report["python"]["ok"])
        self.assertTrue(report["providers"]["ok"])


if __name__ == "__main__":
    unittest.main()
