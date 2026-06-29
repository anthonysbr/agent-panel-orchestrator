from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Dict, Optional

from ..providers import ProviderRegistry, ProviderRunResult, ProviderRunner, WorkspaceMode

ProviderHandler = Callable[
    [str, str, Path, Path, Path],
    ProviderRunResult,
]


class FakeProviderRunner(ProviderRunner):
    """Test double that simulates provider behavior without calling external CLIs."""

    def __init__(
        self,
        registry: ProviderRegistry,
        handlers: Dict[str, ProviderHandler],
        project_root: Path,
        workspace: WorkspaceMode = "project",
        default_handler: Optional[ProviderHandler] = None,
    ) -> None:
        super().__init__(registry, project_root=project_root, workspace=workspace)
        self.handlers = handlers
        self.default_handler = default_handler

    def run(
        self,
        provider_name: str,
        prompt: str,
        output_path: Path,
        log_path: Path,
        timeout_seconds: int,
        empty_retries: Optional[int] = None,
        workspace: Optional[WorkspaceMode] = None,
        project_root: Optional[Path] = None,
    ) -> ProviderRunResult:
        root = (project_root or self.project_root).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = self.handlers.get(provider_name, self.default_handler)
        if handler is None:
            return ProviderRunResult(
                provider=provider_name,
                status="failed",
                output="",
                returncode=1,
                command=["fake", provider_name],
                error=f"no fake handler registered for provider {provider_name!r}",
            )
        result = handler(provider_name, prompt, output_path, log_path, root)
        log_path.write_text(
            f"FAKE PROVIDER: {provider_name}\nSTATUS: {result.status}\n\n{result.output}\n",
            encoding="utf-8",
        )
        return result


def apply_expected_file(project_root: Path, relative_target: str, expected_name: str) -> None:
    source = project_root / "expected" / expected_name
    target = project_root / relative_target
    if not source.is_file():
        raise FileNotFoundError(f"expected fixture file missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def success_output(text: str) -> ProviderRunResult:
    return ProviderRunResult(
        provider="fake",
        status="success",
        output=text,
        returncode=0,
        command=["fake"],
    )
