from __future__ import annotations

import unittest

from panel_core.paths import resolve_panel_executable, resolve_project_root


class PathsTests(unittest.TestCase):
    def test_resolve_project_root_from_repo(self) -> None:
        root = resolve_project_root()
        self.assertTrue((root / "config" / "agents.json").is_file())
        self.assertTrue((root / "skills" / "design" / "skill.json").is_file())

    def test_resolve_panel_executable_from_repo(self) -> None:
        panel = resolve_panel_executable()
        self.assertTrue(panel.is_file())


if __name__ == "__main__":
    unittest.main()
