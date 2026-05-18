"""Load MappingConfig snapshots for registered adapters."""

from __future__ import annotations

import json
from pathlib import Path

from src.exceptions import MonitorError
from src.generator.name_utils import sanitize_client_name
from src.generator.registry import AdapterRegistry
from src.mapping.config import MappingConfig
from src.monitor.codes import MON_CONFIG_NOT_FOUND


def load_mapping_config(
    client_name: str,
    *,
    registry: AdapterRegistry | None = None,
    generated_dir: Path | None = None,
) -> MappingConfig:
    """Load persisted mapping config for a client."""
    reg = registry or AdapterRegistry()
    info = next(
        (a for a in reg.list_adapters() if a.client_name == client_name),
        None,
    )
    if info is None:
        raise MonitorError(
            MON_CONFIG_NOT_FOUND,
            f"No adapter registered for client {client_name!r}",
        )
    _, _, file_stem, _ = sanitize_client_name(client_name)
    base = file_stem[: -len("_adapter")] if file_stem.endswith("_adapter") else file_stem
    config_path = info.adapter_file.parent / f"{base}_mapping_config.json"
    if not config_path.is_file():
        raise MonitorError(
            MON_CONFIG_NOT_FOUND,
            f"Mapping config not found at {config_path}",
            details={"client_name": client_name},
        )
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return MappingConfig.model_validate(raw)


def write_mapping_config(
    config: MappingConfig,
    adapter_dir: Path,
) -> Path:
    """Persist mapping config next to generated adapter."""
    _, _, file_stem, _ = sanitize_client_name(config.client_name)
    base = file_stem[: -len("_adapter")] if file_stem.endswith("_adapter") else file_stem
    path = adapter_dir / f"{base}_mapping_config.json"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(), encoding="utf-8")
    return path
