from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from panel_core.gates import load_gate_specs, run_gates


class GateTests(unittest.TestCase):
    def test_default_gates_when_missing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs = load_gate_specs(Path(tmp))
            self.assertEqual(len(specs), 2)
            self.assertEqual(specs[0]["name"], "compileall")

    def test_load_simple_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            panel_dir = root / ".panel"
            panel_dir.mkdir()
            (panel_dir / "gates.yaml").write_text(
                "gates:\n  - name: echo\n    command: echo ok\n",
                encoding="utf-8",
            )
            specs = load_gate_specs(root)
            self.assertEqual(specs[0]["name"], "echo")

    @mock.patch("panel_core.gates.subprocess.run")
    def test_run_gates_collects_failures(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(returncode=1, stdout="boom")
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_gates(Path(tmp), [{"name": "bad", "command": "false"}])
            self.assertFalse(summary.passed)
            self.assertEqual(summary.results[0].name, "bad")


if __name__ == "__main__":
    unittest.main()
