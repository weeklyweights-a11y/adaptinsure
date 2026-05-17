"""Shared utilities for discovery parsers."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.discovery.profile import FieldInfo, InferredType

_DATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ISO 8601", re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")),
    ("YYYY-MM-DD", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("MM/DD/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("DD/MM/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("MM-DD-YYYY", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")),
    ("YYYYMMDD packed", re.compile(r"^\d{8}$")),
    ("M/D/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
]

_CURRENCY_PATTERN = re.compile(r"^\$?[\d,]+\.\d{2}$|^\$?[\d,]+$")


def python_type_to_inferred(value: Any) -> InferredType:
    """Map a Python value to an inferred type string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (datetime, date)):
        return "datetime" if isinstance(value, datetime) else "date"
    if isinstance(value, Decimal):
        return "decimal"
    return "string"


def detect_string_format(value: str) -> tuple[InferredType, str | None]:
    """Infer type and format pattern from a string value."""
    lowered = value.strip().lower()
    if lowered in {"true", "false", "yes", "no", "1", "0"}:
        return "boolean", None
    for name, pattern in _DATE_PATTERNS:
        if pattern.match(value.strip()):
            inferred: InferredType = "datetime" if "T" in name else "date"
            return inferred, name
    if _CURRENCY_PATTERN.match(value.strip()):
        return "string", "$#,###.##"
    if value.strip().isdigit():
        return "integer", None
    try:
        float(value)
        return "decimal", None
    except ValueError:
        pass
    return "string", None


def merge_field_samples(
    accumulator: dict[str, dict[str, Any]],
    source_name: str,
    value: Any,
    nesting_path: str | None,
    *,
    description: str | None = None,
) -> None:
    """Accumulate samples and metadata for a field key."""
    key = nesting_path or source_name
    if key not in accumulator:
        accumulator[key] = {
            "source_name": source_name,
            "nesting_path": nesting_path,
            "samples": [],
            "nullable": False,
            "types": set(),
            "format_patterns": set(),
            "description": description,
        }
    entry = accumulator[key]
    if description and not entry.get("description"):
        entry["description"] = description
    if value is None:
        entry["nullable"] = True
        entry["types"].add("null")
        return
    inferred = python_type_to_inferred(value)
    entry["types"].add(inferred)
    if inferred == "string" and isinstance(value, str):
        str_type, fmt = detect_string_format(value)
        entry["types"].add(str_type)
        if fmt:
            entry["format_patterns"].add(fmt)
        sample = value
    else:
        sample = str(value)
    samples: list[str] = entry["samples"]
    if sample not in samples and len(samples) < 5:
        samples.append(sample)


def accumulator_to_fields(accumulator: dict[str, dict[str, Any]]) -> list[FieldInfo]:
    """Convert accumulated field data to FieldInfo list."""
    fields: list[FieldInfo] = []
    for entry in accumulator.values():
        types: set[str] = entry["types"] - {"null"}
        if len(types) > 1:
            inferred_type: InferredType = "string"
        elif types:
            inferred_type = next(iter(types))  # type: ignore[assignment]
        else:
            inferred_type = "null" if entry["nullable"] else "unknown"
        format_patterns = entry.get("format_patterns") or set()
        format_pattern = next(iter(format_patterns), None) if len(format_patterns) == 1 else None
        nesting = entry.get("nesting_path")
        if nesting == entry["source_name"]:
            nesting = None
        fields.append(
            FieldInfo(
                source_name=entry["source_name"],
                inferred_type=inferred_type,
                sample_values=entry["samples"][:5],
                nullable=entry["nullable"],
                format_pattern=format_pattern,
                description=entry.get("description"),
                nesting_path=nesting,
                confidence=0.5,
            )
        )
    return fields


def flatten_json_records(
    records: list[dict[str, Any]],
    prefix: str = "",
) -> dict[str, dict[str, Any]]:
    """Flatten nested JSON records into field accumulator."""
    accumulator: dict[str, dict[str, Any]] = {}

    def walk(obj: Any, path: str, name: str) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                child_path = f"{path}.{key}" if path else key
                if isinstance(val, dict):
                    walk(val, child_path, key)
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    array_path = f"{child_path}[]"
                    for item in val:
                        if isinstance(item, dict):
                            walk(item, array_path, key)
                else:
                    merge_field_samples(
                        accumulator,
                        key,
                        val,
                        child_path if path else key,
                    )
        elif isinstance(obj, list):
            for item in obj:
                walk(item, path, name)

    for record in records:
        walk(record, prefix, "")
    return accumulator
