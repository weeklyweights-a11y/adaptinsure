"""CSV parser for the Discovery Engine."""

from __future__ import annotations

import csv
import io

from src.discovery.parsers._utils import detect_string_format
from src.discovery.parsers.types import ParserResult
from src.discovery.profile import FieldInfo, InferredType

_BOOL_VALUES = frozenset({"true", "false", "yes", "no", "1", "0"})


def parse_csv(raw_input: str) -> ParserResult:
    """Parse CSV/TSV data and extract field information."""
    text = raw_input
    for encoding_attempt in ("utf-8", "latin-1", "cp1252"):
        try:
            text.encode(encoding_attempt)
            break
        except UnicodeEncodeError:
            continue

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        dialect = csv.excel
        has_header = True

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    if not rows:
        return ParserResult(fields=[], record_count=0, raw_sample=None, parser_notes=[])

    notes: list[str] = []
    use_header = has_header or _first_row_looks_like_header(rows)
    if use_header:
        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
    else:
        headers = [f"col_{i}" for i in range(len(rows[0]))]
        data_rows = rows
        notes.append("No header row detected; synthetic column names generated")

    record_count = len(data_rows)
    columns: list[list[str]] = [[] for _ in headers]
    for row in data_rows:
        for idx, header in enumerate(headers):
            if idx < len(row):
                columns[idx].append(row[idx].strip())
            else:
                columns[idx].append("")

    fields: list[FieldInfo] = []
    for header, values in zip(headers, columns, strict=True):
        non_empty = [v for v in values if v]
        nullable = len(non_empty) < len(values)
        inferred_type, format_pattern = _infer_column_type(non_empty)
        samples = list(dict.fromkeys(non_empty))[:5]
        fields.append(
            FieldInfo(
                source_name=header,
                inferred_type=inferred_type,
                sample_values=samples,
                nullable=nullable,
                format_pattern=format_pattern,
                confidence=0.5,
            )
        )

    raw_sample = dict(zip(headers, data_rows[0], strict=False)) if data_rows else None
    return ParserResult(
        fields=fields,
        record_count=record_count,
        raw_sample=raw_sample,
        parser_notes=notes,
    )


def _first_row_looks_like_header(rows: list[list[str]]) -> bool:
    """Heuristic: first row is header if every cell looks like a column label."""
    if len(rows) < 2:
        return False
    first = rows[0]
    return all(_looks_like_header_cell(cell) for cell in first)


def _looks_like_header_cell(cell: str) -> bool:
    """Return True if cell looks like a column name rather than data."""
    stripped = cell.strip()
    if not stripped:
        return False
    return not stripped.replace(".", "", 1).isdigit()


def _infer_column_type(values: list[str]) -> tuple[InferredType, str | None]:
    """Infer column type from sample values."""
    if not values:
        return "unknown", None
    if all(len(v) == 8 and v.isdigit() for v in values):
        return "date", "YYYYMMDD packed"
    if all(v.isdigit() for v in values):
        return "integer", None
    types: set[InferredType] = set()
    format_patterns: set[str] = set()
    for value in values:
        inferred, fmt = detect_string_format(value)
        types.add(inferred)
        if fmt:
            format_patterns.add(fmt)
    if types == {"integer"}:
        return "integer", None
    if types == {"decimal"} or types <= {"integer", "decimal"}:
        return "decimal", None
    if len(types) == 1:
        inferred_type = next(iter(types))
        fmt = next(iter(format_patterns), None) if len(format_patterns) == 1 else None
        return inferred_type, fmt
    return "string", None
