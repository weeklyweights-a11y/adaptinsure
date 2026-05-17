"""Shared types for discovery parsers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.discovery.profile import FieldInfo


@dataclass(frozen=True)
class ParserResult:
    """Result from a data format parser."""

    fields: list[FieldInfo]
    record_count: int
    raw_sample: dict[str, Any] | str | None
    parser_notes: list[str]
