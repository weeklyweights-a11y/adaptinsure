"""File-based knowledge base for proven field mappings."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.config import get_settings
from src.mapping.config import FieldMapping

logger = logging.getLogger(__name__)

_MIN_STORE_CONFIDENCE = 0.8


class _StoredMappingFile(BaseModel):
    """On-disk knowledge base file format."""

    model_config = ConfigDict(strict=True)

    client_name: str
    source_format: str
    stored_at: datetime
    mappings: list[FieldMapping] = Field(default_factory=list)


class MappingKnowledgeBase:
    """Persist and retrieve proven mappings as JSON files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize with optional directory override."""
        settings = get_settings()
        self._base_dir = base_dir or settings.knowledge_base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, client_name: str, source_format: str) -> Path:
        safe_name = client_name.replace("/", "_")
        return self._base_dir / f"{safe_name}_{source_format}.json"

    def _load_all_files(self, source_format: str) -> list[_StoredMappingFile]:
        """Load all KB files for a given source format."""
        files: list[_StoredMappingFile] = []
        pattern = f"*_{source_format}.json"
        for path in self._base_dir.glob(pattern):
            try:
                files.append(
                    _StoredMappingFile.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.warning("Skipping invalid KB file %s: %s", path, exc)
        return files

    def store(
        self,
        client_name: str,
        source_format: str,
        mappings: list[FieldMapping],
    ) -> None:
        """Store high-confidence mappings for a client and format."""
        proven = [m for m in mappings if m.confidence >= _MIN_STORE_CONFIDENCE]
        payload = _StoredMappingFile(
            client_name=client_name,
            source_format=source_format,
            stored_at=datetime.now(UTC),
            mappings=proven,
        )
        path = self._file_path(client_name, source_format)
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Stored %s mappings for %s", len(proven), path.name)

    def lookup(self, source_field_name: str, source_format: str) -> FieldMapping | None:
        """Return highest-confidence mapping across all clients for a format."""
        best: FieldMapping | None = None
        for stored in self._load_all_files(source_format):
            for mapping in stored.mappings:
                if mapping.source_field != source_field_name:
                    continue
                if best is None or mapping.confidence > best.confidence:
                    best = mapping
        return best

    def get_known_mappings(self, source_format: str) -> list[FieldMapping]:
        """Return all stored mappings for a format (all clients)."""
        result: list[FieldMapping] = []
        for stored in self._load_all_files(source_format):
            result.extend(stored.mappings)
        return result

    def list_clients(self) -> list[str]:
        """Return distinct client names from KB filenames."""
        clients: set[str] = set()
        for path in self._base_dir.glob("*_*.json"):
            name = path.stem
            if "_" not in name:
                continue
            client, _fmt = name.rsplit("_", 1)
            clients.add(client)
        return sorted(clients)
