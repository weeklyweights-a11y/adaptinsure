"""Registry for tracking and loading generated adapters."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.config import get_settings
from src.exceptions import GenerationError
from src.generator.codes import GEN_ADAPTER_NOT_FOUND, GEN_IMPORT_FAILED
from src.generator.engine import GenerationResult
from src.generator.name_utils import sanitize_client_name
from src.mapping.config import MappingConfig

logger = logging.getLogger(__name__)


class AdapterInfo(BaseModel):
    """Metadata for a registered generated adapter."""

    model_config = ConfigDict(strict=True)

    client_name: Annotated[str, Field(description="Client identifier")]
    class_name: Annotated[str, Field(description="Adapter class name")]
    source_format: Annotated[str, Field(description="Source format")]
    adapter_file: Annotated[Path, Field(description="Path to adapter module")]
    registered_at: Annotated[datetime, Field(description="Registration time UTC")]
    field_count: Annotated[int, Field(ge=0)]
    transform_count: Annotated[int, Field(ge=0)]


class AdapterRegistry:
    """Persist and load generated adapter metadata."""

    def __init__(self, registry_path: Path | None = None) -> None:
        """Load registry state from disk if present."""
        settings = get_settings()
        self._registry_path = registry_path or (
            settings.generated_adapters_dir / "registry.json"
        )
        self._adapters: dict[str, AdapterInfo] = {}
        self._class_cache: dict[str, type] = {}
        self._project_root = Path(__file__).resolve().parents[2]
        self._load()

    def register(self, result: GenerationResult, config: MappingConfig) -> None:
        """Register a generated adapter and persist config snapshot."""
        _, _, file_stem, _ = sanitize_client_name(config.client_name)
        base = file_stem[: -len("_adapter")] if file_stem.endswith("_adapter") else file_stem
        config_path = result.adapter_file.parent / f"{base}_mapping_config.json"

        config_path.write_text(config.model_dump_json(), encoding="utf-8")

        info = AdapterInfo(
            client_name=config.client_name,
            class_name=result.class_name,
            source_format=config.source_format,
            adapter_file=result.adapter_file,
            registered_at=datetime.now(UTC),
            field_count=result.field_count,
            transform_count=result.transform_count,
        )
        self._adapters[config.client_name] = info
        self._class_cache.pop(config.client_name, None)
        self._save()

    def get_adapter_class(self, client_name: str) -> type:
        """Import and return the generated adapter class (cached)."""
        if client_name in self._class_cache:
            return self._class_cache[client_name]

        info = self._adapters.get(client_name)
        if info is None:
            raise GenerationError(
                GEN_ADAPTER_NOT_FOUND,
                f"No adapter registered for client {client_name!r}",
            )

        adapter_path = info.adapter_file.resolve()
        paths_to_add = [str(self._project_root), str(adapter_path.parent)]
        for path_str in paths_to_add:
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

        module_name = adapter_path.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, adapter_path)
            if spec is None or spec.loader is None:
                msg = f"Could not load spec for {adapter_path}"
                raise ImportError(msg)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            adapter_cls = getattr(module, info.class_name)
        except Exception as exc:
            raise GenerationError(
                GEN_IMPORT_FAILED,
                f"Failed to import adapter for {client_name!r}",
                details={"error": str(exc), "path": str(adapter_path)},
            ) from exc

        self._class_cache[client_name] = adapter_cls
        return adapter_cls

    def list_adapters(self) -> list[AdapterInfo]:
        """Return metadata for all registered adapters."""
        return list(self._adapters.values())

    def get_adapter_for_format(self, source_format: str) -> list[AdapterInfo]:
        """Return adapters that handle the given source format."""
        return [
            info
            for info in self._adapters.values()
            if info.source_format == source_format
        ]

    def remove(self, client_name: str) -> bool:
        """Remove an adapter from the registry."""
        if client_name not in self._adapters:
            return False
        del self._adapters[client_name]
        self._class_cache.pop(client_name, None)
        self._save()
        return True

    def _save(self) -> None:
        """Persist registry to JSON."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            name: {
                **info.model_dump(mode="json"),
                "adapter_file": str(info.adapter_file),
            }
            for name, info in self._adapters.items()
        }
        self._registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load registry from JSON if it exists."""
        if not self._registry_path.exists():
            return
        try:
            raw = json.loads(self._registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid registry file at %s", self._registry_path)
            return
        for client_name, data in raw.items():
            data["adapter_file"] = Path(data["adapter_file"])
            data["registered_at"] = datetime.fromisoformat(data["registered_at"])
            self._adapters[client_name] = AdapterInfo.model_validate(data)
