from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import CommandConfig, OrchestratorConfig, ProviderConfig


@dataclass(frozen=True)
class Detection:
    name: str
    display_name: str
    binary: str
    available: bool
    path: Optional[str]
    version: Optional[str]
    kind: str


@dataclass(frozen=True)
class ProviderRunResult:
    provider: str
    status: str
    output: str
    returncode: Optional[int]
    command: List[str]
    error: str = ""


class ProviderRegistry:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def detect_command(self, command: CommandConfig, kind: str) -> Detection:
        binary_path = shutil.which(command.binary)
        if binary_path is None:
            return Detection(
                name=command.name,
                display_name=command.display_name,
                binary=command.binary,
                available=False,
                path=None,
                version=None,
                kind=kind,
            )

        version = None
        if command.version_args:
            try:
                completed = subprocess.run(
                    [binary_path] + command.version_args,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=5,
                    check=False,
                )
                version = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else None
            except Exception as exc:  # pragma: no cover
                version = f"version check failed: {exc}"

        return Detection(
            name=command.name,
            display_name=command.display_name,
            binary=command.binary,
            available=True,
            path=binary_path,
            version=version,
            kind=kind,
        )

    def detect_providers(self) -> Dict[str, Detection]:
        return {
            name: self.detect_command(provider, "provider")
            for name, provider in self.config.providers.items()
        }

    def detect_external_tools(self) -> Dict[str, Detection]:
        return {
            name: self.detect_command(tool, "external_tool")
            for name, tool in self.config.external_tools.items()
        }

    def detect_all(self) -> Dict[str, Detection]:
        detections = self.detect_providers()
        detections.update(self.detect_external_tools())
        return detections

    def available_provider_names(self) -> List[str]:
        return [name for name, detected in self.detect_providers().items() if detected.available]

    def require_provider(self, name: str) -> ProviderConfig:
        try:
            return self.config.providers[name]
        except KeyError as exc:
            known = ", ".join(sorted(self.config.providers))
            raise ValueError(f"unknown provider {name!r}; known providers: {known}") from exc


WorkspaceMode = str  # "scratch" | "project"


class ProviderRunner:
    def __init__(
        self,
        registry: ProviderRegistry,
        project_root: Optional[Path] = None,
        workspace: WorkspaceMode = "scratch",
    ) -> None:
        self.registry = registry
        self.project_root = (project_root or Path.cwd()).resolve()
        self.workspace = workspace

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
        mode = workspace or self.workspace
        root = (project_root or self.project_root).resolve()
        if mode not in {"scratch", "project"}:
            raise ValueError(f"unsupported workspace mode: {mode!r}")

        provider = self.registry.require_provider(provider_name)
        detection = self.registry.detect_command(provider, "provider")
        if not detection.available:
            return ProviderRunResult(
                provider=provider_name,
                status="missing",
                output="",
                returncode=None,
                command=[],
                error=f"{provider.display_name} binary {provider.binary!r} was not found in PATH",
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        retry_limit = self._empty_retry_limit() if empty_retries is None else max(0, empty_retries)
        max_attempts = retry_limit + 1

        for attempt in range(max_attempts):
            if mode == "project":
                result = self._run_once(
                    provider,
                    provider_name,
                    prompt,
                    output_path,
                    log_path,
                    timeout_seconds,
                    work_dir=root,
                    project_root=root,
                    attempt=attempt,
                )
            else:
                with tempfile.TemporaryDirectory(prefix=f"panel-{provider_name}.") as scratch:
                    scratch_path = Path(scratch)
                    result = self._run_once(
                        provider,
                        provider_name,
                        prompt,
                        output_path,
                        log_path,
                        timeout_seconds,
                        work_dir=scratch_path,
                        project_root=root,
                        attempt=attempt,
                    )
            if result.status != "empty" or attempt >= max_attempts - 1:
                return result

        raise RuntimeError("provider run ended without a result")

    def _run_once(
        self,
        provider: ProviderConfig,
        provider_name: str,
        prompt: str,
        output_path: Path,
        log_path: Path,
        timeout_seconds: int,
        work_dir: Path,
        project_root: Path,
        attempt: int,
    ) -> ProviderRunResult:
        command = self._render_command(
            provider.command,
            prompt=prompt,
            output_path=output_path,
            scratch_dir=work_dir,
            project_root=project_root,
        )
        try:
            completed = self._execute(provider, command, prompt, work_dir, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            log_path.write_text(str(exc), encoding="utf-8")
            return ProviderRunResult(
                provider=provider_name,
                status="timeout",
                output="",
                returncode=None,
                command=command,
                error=f"provider timed out after {timeout_seconds} seconds",
            )

        log_text = (
            "COMMAND: " + " ".join(command) + "\n\n"
            + "STDOUT:\n" + (completed.stdout or "")
            + "\n\nSTDERR:\n" + (completed.stderr or "")
        )
        if attempt:
            log_text = f"ATTEMPT: {attempt + 1}\n\n" + log_text
        log_path.write_text(log_text, encoding="utf-8")

        if provider.mode == "stdin_to_output_file":
            output = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        else:
            output = completed.stdout or ""
            output_path.write_text(output, encoding="utf-8")

        if completed.returncode != 0:
            return ProviderRunResult(
                provider=provider_name,
                status="failed",
                output=output,
                returncode=completed.returncode,
                command=command,
                error=(completed.stderr or completed.stdout or "").strip(),
            )

        if not output.strip():
            return ProviderRunResult(
                provider=provider_name,
                status="empty",
                output=output,
                returncode=completed.returncode,
                command=command,
                error="provider completed but produced no output",
            )

        return ProviderRunResult(
            provider=provider_name,
            status="success",
            output=output,
            returncode=completed.returncode,
            command=command,
        )

    @staticmethod
    def _empty_retry_limit() -> int:
        raw = os.environ.get("PANEL_PROVIDER_EMPTY_RETRIES", "1").strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return 1

    def _execute(
        self,
        provider: ProviderConfig,
        command: List[str],
        prompt: str,
        scratch_dir: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        if provider.mode in {"stdin_to_output_file", "stdin_stdout"}:
            return subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(scratch_dir),
                timeout=timeout_seconds,
                check=False,
            )
        if provider.mode == "arg_stdout":
            return subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(scratch_dir),
                timeout=timeout_seconds,
                check=False,
            )
        raise ValueError(f"unsupported provider mode: {provider.mode}")

    def _render_command(
        self,
        command: Iterable[str],
        prompt: str,
        output_path: Path,
        scratch_dir: Path,
        project_root: Path,
    ) -> List[str]:
        values = {
            "prompt": prompt,
            "output_file": str(output_path),
            "scratch_dir": str(scratch_dir),
            "project_root": str(project_root),
        }
        return [part.format(**values) for part in command]
