"""Parse incoming insurer batches into record dicts for drift detection."""

from __future__ import annotations

import csv
import io
import json

from lxml import etree

from src.discovery.parsers import decode_raw_input, detect_format
from src.exceptions import MonitorError
from src.monitor.codes import MON_PARSE_FAILED

_RECORD_TAGS = frozenset({"Claim", "ClaimsOccurrence"})


def parse_incoming_records(
    raw_input: str | bytes,
) -> tuple[str, list[dict[str, object]]]:
    """Detect format and return records as flat dicts per claim."""
    if isinstance(raw_input, bytes):
        text, _encoding = decode_raw_input(raw_input)
    else:
        text = raw_input
    if not text.strip():
        raise MonitorError(MON_PARSE_FAILED, "Incoming data is empty")
    fmt = detect_format(text)
    if fmt == "json":
        return "json", _parse_json_records(text)
    if fmt == "xml":
        return "xml", _parse_xml_records(text)
    if fmt in {"csv", "fixed_width"}:
        return "csv", _parse_csv_records(text)
    raise MonitorError(
        MON_PARSE_FAILED,
        f"Unsupported format for monitor parsing: {fmt}",
    )


def _parse_json_records(text: str) -> list[dict[str, object]]:
    """Parse JSON array or object into record list."""
    data = json.loads(text)
    if isinstance(data, list):
        return [_flatten_record(dict(item)) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [_flatten_record(dict(data))]
    raise MonitorError(MON_PARSE_FAILED, "JSON root must be object or array")


def _flatten_record(record: dict[str, object]) -> dict[str, object]:
    """Flatten one level of nesting for top-level dict values."""
    flat: dict[str, object] = {}
    for key, val in record.items():
        if isinstance(val, dict):
            for sub_key, sub_val in val.items():
                if not isinstance(sub_val, dict):
                    flat[sub_key] = sub_val
            flat[key] = val
        else:
            flat[key] = val
    return flat


def _parse_csv_records(text: str) -> list[dict[str, object]]:
    """Parse CSV text into list of row dicts."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            stream = io.StringIO(text)
            reader = csv.DictReader(stream)
            rows = [dict(row) for row in reader]
            if rows:
                return rows
        except Exception:
            continue
    raise MonitorError(MON_PARSE_FAILED, "Failed to parse CSV records")


def _parse_xml_records(text: str) -> list[dict[str, object]]:
    """Parse ACORD-style XML into flat record dicts."""
    root = etree.fromstring(text.encode("utf-8"))
    records: list[dict[str, object]] = []
    for element in root.iter():
        local = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if local not in _RECORD_TAGS:
            continue
        record: dict[str, object] = {}
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child):
                nested: dict[str, object] = {}
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                    val = (sub.text or "").strip()
                    nested[sub_tag] = val
                    record[sub_tag] = val
                record[tag] = nested
            else:
                record[tag] = (child.text or "").strip()
        if record:
            records.append(record)
    if not records:
        raise MonitorError(MON_PARSE_FAILED, "No XML claim records found")
    return records


def get_field_value(record: dict[str, object], field_name: str) -> object | None:
    """Read a field from a record, including top-level flat keys."""
    if field_name in record:
        return record[field_name]
    return None
