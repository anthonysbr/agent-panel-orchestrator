from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from panel_core.cli import main


class CliTests(unittest.TestCase):
    def test_export_rules_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                code = main(["export-rules", "--target", tmp])
            target = Path(tmp)

            self.assertEqual(code, 0)
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertTrue((target / ".cursor" / "rules" / "agent-panel-orchestrator.mdc").exists())
            self.assertTrue((target / ".claude" / "skills" / "agent-panel" / "SKILL.md").exists())

            agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Agent Panel Orchestrator", agents)
            self.assertIn("Anthony Batista", agents)
            self.assertNotIn("Pinned workflow source", agents)

    def test_doctor_json(self) -> None:
        buffer = StringIO()
        with mock.patch("sys.stdout", buffer):
            code = main(["doctor", "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertIn("python", payload)
        self.assertIn(code, (0, 1))

    def test_run_dry_run_with_yes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            buffer = StringIO()
            with mock.patch("sys.stdout", buffer):
                code = main(
                    [
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
                        "test",
                    ]
                )
            self.assertEqual(0, code)
            self.assertIn("Run directory:", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
