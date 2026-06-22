from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping

from .paths import PROJECT_ROOT
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "agents.json"


@dataclass(frozen=True)
class CommandConfig:
    name: str
    display_name: str
    binary: str
    version_args: List[str]


@dataclass(frozen=True)
class ProviderConfig(CommandConfig):
    mode: str
    command: List[str]


@dataclass(frozen=True)
class OrchestratorConfig:
    providers: Dict[str, ProviderConfig]
    external_tools: Dict[str, CommandConfig]


def _as_string_list(value: object, field_name: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> OrchestratorConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("agents config must be a JSON object")

    providers: Dict[str, ProviderConfig] = {}
    for name, item in raw.get("providers", {}).items():
        if not isinstance(item, Mapping):
            raise ValueError(f"provider {name} must be an object")
        providers[name] = ProviderConfig(
            name=name,
            display_name=str(item["display_name"]),
            binary=str(item["binary"]),
            version_args=_as_string_list(item.get("version_args", []), f"{name}.version_args"),
            mode=str(item["mode"]),
            command=_as_string_list(item["command"], f"{name}.command"),
        )

    external_tools: Dict[str, CommandConfig] = {}
    for name, item in raw.get("external_tools", {}).items():
        if not isinstance(item, Mapping):
            raise ValueError(f"external tool {name} must be an object")
        external_tools[name] = CommandConfig(
            name=name,
            display_name=str(item["display_name"]),
            binary=str(item["binary"]),
            version_args=_as_string_list(item.get("version_args", []), f"{name}.version_args"),
        )

    return OrchestratorConfig(providers=providers, external_tools=external_tools)
