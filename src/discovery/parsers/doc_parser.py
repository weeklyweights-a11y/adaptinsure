"""Data dictionary document parser for the Discovery Engine."""

from __future__ import annotations

import re

from src.discovery.profile import FieldInfo

_MARKDOWN_SEP = re.compile(r"^\s*\|?[\s\-:|]+\|?\s*$")


def parse_data_dictionary(raw_input: str) -> list[FieldInfo]:
    """Parse markdown/TSV/key-value data dictionaries into FieldInfo list."""
    stripped = raw_input.strip()
    if not stripped:
        return []

    if "|" in stripped and _looks_like_markdown_table(stripped):
        return _parse_markdown_table(stripped)
    if "\t" in stripped.splitlines()[0]:
        return _parse_tsv_table(stripped)
    return _parse_key_value(stripped)


def _looks_like_markdown_table(text: str) -> bool:
    """Return True if text contains a markdown table separator."""
    for line in text.splitlines():
        if _MARKDOWN_SEP.match(line) and "-" in line:
            return True
    return False


def _parse_markdown_table(text: str) -> list[FieldInfo]:
    """Parse a markdown pipe table."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_line = lines[0]
    headers = [cell.strip() for cell in header_line.strip("|").split("|")]
    data_start = 2 if len(lines) > 1 and _MARKDOWN_SEP.match(lines[1]) else 1
    return _rows_to_fields(headers, lines[data_start:])


def _parse_tsv_table(text: str) -> list[FieldInfo]:
    """Parse a tab-separated table."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    headers = lines[0].split("\t")
    return _rows_to_fields(headers, lines[1:])


def _parse_key_value(text: str) -> list[FieldInfo]:
    """Parse FIELD: description or FIELD - description lines."""
    fields: list[FieldInfo] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            name, _, desc = line.partition(":")
        elif " - " in line:
            name, _, desc = line.partition(" - ")
        else:
            continue
        fields.append(
            FieldInfo(
                source_name=name.strip(),
                inferred_type="unknown",
                description=desc.strip(),
                confidence=0.5,
            )
        )
    return fields


def _rows_to_fields(headers: list[str], rows: list[str]) -> list[FieldInfo]:
    """Convert table headers and rows to FieldInfo entries."""
    normalized = [h.lower().replace(" ", "_") for h in headers]
    name_idx = _find_column(normalized, ("field", "field_name", "name", "column"))
    type_idx = _find_column(normalized, ("type", "data_type"))
    desc_idx = _find_column(normalized, ("description", "desc", "meaning"))
    fmt_idx = _find_column(normalized, ("format", "pattern"))

    fields: list[FieldInfo] = []
    for row_line in rows:
        if "|" in row_line:
            cells = [c.strip() for c in row_line.strip("|").split("|")]
        else:
            cells = row_line.split("\t")
        if not cells:
            continue
        source_name = cells[name_idx].strip() if name_idx is not None else cells[0].strip()
        inferred = "unknown"
        if type_idx is not None and type_idx < len(cells):
            type_val = cells[type_idx].strip().lower()
            if type_val in {
                "string",
                "integer",
                "decimal",
                "boolean",
                "date",
                "datetime",
            }:
                inferred = type_val
        description = None
        if desc_idx is not None and desc_idx < len(cells):
            description = cells[desc_idx].strip() or None
        format_pattern = None
        if fmt_idx is not None and fmt_idx < len(cells):
            format_pattern = cells[fmt_idx].strip() or None
        fields.append(
            FieldInfo(
                source_name=source_name,
                inferred_type=inferred,  # type: ignore[arg-type]
                description=description,
                format_pattern=format_pattern,
                confidence=0.5,
            )
        )
    return fields


def _find_column(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    """Find column index matching candidate header names."""
    for idx, header in enumerate(headers):
        if header in candidates:
            return idx
    return None
