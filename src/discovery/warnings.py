"""Discovery warning and nested-structure helpers."""

from __future__ import annotations

from src.discovery.profile import FieldInfo


def build_discovery_warnings(fields: list[FieldInfo]) -> list[str]:
    """Build human-readable warnings from field analysis."""
    warnings: list[str] = []
    no_samples = [f.source_name for f in fields if not f.sample_values]
    if no_samples:
        count = len(no_samples)
        warnings.append(f"{count} field(s) have no sample values")
    for field in fields:
        if len(field.sample_values) < 2:
            continue
        patterns: set[str] = set()
        for sample in field.sample_values:
            if "/" in sample and "-" in sample:
                patterns.add("mixed separators")
            elif "-" in sample:
                patterns.add("dash dates")
            elif "/" in sample:
                patterns.add("slash dates")
        if len(patterns) > 1:
            warnings.append(f"Field '{field.source_name}' has mixed date formats")
    return warnings


def collect_nested_structures(fields: list[FieldInfo]) -> list[str]:
    """Collect nested array/object names from nesting_path values."""
    names: set[str] = set()
    for field in fields:
        if not field.nesting_path:
            continue
        parts = field.nesting_path.replace("[]", "").split(".")
        for part in parts:
            if part and part != field.source_name:
                names.add(part)
        if "[]" in field.nesting_path:
            segment = field.nesting_path.split("[")[-1].split("]")[0]
            if segment.startswith("."):
                segment = segment[1:]
            if segment:
                names.add(segment.split(".")[0])
    for field in fields:
        if field.nesting_path and "[]" in field.nesting_path:
            base = field.nesting_path.split("[]")[0]
            if base:
                names.add(base.split(".")[-1])
    return sorted(names)
