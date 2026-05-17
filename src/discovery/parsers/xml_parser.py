"""XML parser with ACORD detection for the Discovery Engine."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from src.discovery.parsers._utils import (
    accumulator_to_fields,
    detect_string_format,
    merge_field_samples,
)
from src.discovery.parsers.types import ParserResult

ACORD_NAMESPACE_FRAGMENT = "ACORD.org"


def detect_acord_version(raw_input: str) -> str | None:
    """Detect ACORD version from XML input."""
    try:
        root = ET.fromstring(raw_input)
    except ET.ParseError:
        return None
    root_tag = root.tag
    if ACORD_NAMESPACE_FRAGMENT not in root_tag and not _has_acord_namespace(root):
        return None
    version = root.get("Version") or root.get("version")
    if version:
        return version
    for elem in root.iter():
        if elem.get("Version"):
            return elem.get("Version")
    return "unknown"


def _has_acord_namespace(root: ET.Element) -> bool:
    """Return True if any element uses an ACORD namespace."""
    for elem in root.iter():
        if ACORD_NAMESPACE_FRAGMENT in elem.tag:
            return True
    return False


def _strip_namespace(tag: str) -> str:
    """Remove XML namespace prefix from tag."""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.rsplit(":", 1)[-1]
    return tag


def parse_xml(raw_input: str) -> ParserResult:
    """Parse XML and extract field information."""
    root = ET.fromstring(raw_input)
    accumulator: dict[str, dict[str, Any]] = {}
    repeating_tags: set[str] = set()
    record_count = 0

    def walk(element: ET.Element, ancestors: list[str]) -> None:
        nonlocal record_count
        tag = _strip_namespace(element.tag)
        path_parts = ancestors + [tag]
        nesting_path = ".".join(path_parts)
        text = (element.text or "").strip()

        if text:
            inferred, fmt = detect_string_format(text)
            merge_field_samples(
                accumulator,
                tag,
                text,
                nesting_path,
                description=f"QName: {element.tag}",
            )
            entry = accumulator.get(nesting_path) or accumulator.get(tag)
            if entry and inferred != "string":
                entry["types"] = {inferred}
                if fmt:
                    entry["format_patterns"] = {fmt}

        for attr_name, attr_value in element.attrib.items():
            attr_key = f"{tag}@{attr_name}"
            attr_path = f"{nesting_path}@{attr_name}"
            merge_field_samples(
                accumulator,
                attr_key,
                attr_value,
                attr_path,
                description=f"Attribute on {element.tag}",
            )

        child_tags = [_strip_namespace(child.tag) for child in element]
        for child_tag in set(child_tags):
            if child_tags.count(child_tag) > 1:
                repeating_tags.add(child_tag)

        if not list(element) and not text and not element.attrib:
            merge_field_samples(accumulator, tag, None, nesting_path)

        for child in element:
            walk(child, path_parts)

    walk(root, [])
    children = list(root)
    record_count = len(children) if children else 1

    fields = accumulator_to_fields(accumulator)
    notes: list[str] = []
    acord_version = detect_acord_version(raw_input)
    if acord_version:
        notes.append(f"ACORD namespace detected (version: {acord_version})")
    if repeating_tags:
        notes.append(f"Repeating elements detected: {', '.join(sorted(repeating_tags))}")

    raw_sample = ET.tostring(root, encoding="unicode")[:500]
    return ParserResult(
        fields=fields,
        record_count=record_count,
        raw_sample=raw_sample,
        parser_notes=notes,
    )
