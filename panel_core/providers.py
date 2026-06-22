from __future__ import annotations

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


class ProviderRunner:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def run(
        self,
        provider_name: str,
        prompt: str,
        output_path: Path,
        log_path: Path,
        timeout_seconds: int,
    ) -> ProviderRunResult:
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

        with tempfile.TemporaryDirectory(prefix=f"panel-{provider_name}.") as scratch:
            command = self._render_command(
                provider.command,
                prompt=prompt,
                output_path=output_path,
                scratch_dir=Path(scratch),
            )
            try:
                completed = self._execute(provider, command, prompt, Path(scratch), timeout_seconds)
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

            log_path.write_text(
                "COMMAND: " + " ".join(command) + "\n\n"
                + "STDOUT:\n" + (completed.stdout or "")
                + "\n\nSTDERR:\n" + (completed.stderr or ""),
                encoding="utf-8",
            )

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
    ) -> List[str]:
        values = {
            "prompt": prompt,
            "output_file": str(output_path),
            "scratch_dir": str(scratch_dir),
        }
        return [part.format(**values) for part in command]
