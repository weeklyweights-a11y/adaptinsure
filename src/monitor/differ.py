"""Schema differ — compare incoming records to expected schema."""

from __future__ import annotations

import statistics
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.discovery.parsers._utils import detect_string_format, python_type_to_inferred
from src.mapping.schema_registry import CRITICAL_REQUIRED_TARGETS
from src.monitor.expected_schema import ExpectedField, ExpectedSchema
from src.monitor.records import get_field_value

PRESENCE_THRESHOLD = 0.95
RENAME_RATIO_THRESHOLD = 0.6
DISTRIBUTION_SHIFT_RATIO = 0.20


class DiffType(StrEnum):
    """Categories of schema drift."""

    FIELD_RENAMED = "field_renamed"
    FIELD_REMOVED = "field_removed"
    FIELD_ADDED = "field_added"
    TYPE_CHANGED = "type_changed"
    FORMAT_CHANGED = "format_changed"
    ENUM_VALUE_ADDED = "enum_value_added"
    NULLABLE_CHANGED = "nullable_changed"
    DISTRIBUTION_SHIFTED = "distribution_shifted"


class SchemaDiff(BaseModel):
    """A single detected drift between expected and incoming data."""

    model_config = ConfigDict(strict=True)

    diff_type: Annotated[DiffType, Field(description="Drift category")]
    field_name: Annotated[str, Field(description="Affected source field")]
    severity: Annotated[str, Field(description="critical, warning, or info")]
    description: Annotated[str, Field(description="Human-readable explanation")]
    old_value: Annotated[str | None, Field(default=None)]
    new_value: Annotated[str | None, Field(default=None)]
    affected_records: Annotated[int, Field(ge=0)]
    total_records: Annotated[int, Field(ge=0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    suggested_rename: Annotated[str | None, Field(default=None)]
    target_field: Annotated[str | None, Field(default=None)]


class SchemaDiffer:
    """Compare incoming record batches against an expected schema."""

    def diff(
        self,
        expected: ExpectedSchema,
        incoming_records: list[dict[str, object]],
    ) -> list[SchemaDiff]:
        """Return all detected drifts sorted by severity."""
        if not incoming_records:
            return []
        total = len(incoming_records)
        diffs: list[SchemaDiff] = []
        expected_names = {f.field_name for f in expected.fields}
        incoming_keys = _collect_keys(incoming_records)

        removed, renamed_pairs = self._detect_removed_and_renamed(
            expected, incoming_records, incoming_keys, expected_names, total
        )
        diffs.extend(removed)
        diffs.extend(renamed_pairs)

        renamed_old = {d.field_name for d in renamed_pairs}
        removed_names = {d.field_name for d in removed}
        for field in expected.fields:
            if field.field_name in renamed_old or field.field_name in removed_names:
                continue
            if field.field_name not in incoming_keys:
                continue
            diffs.extend(self._diff_existing_field(field, incoming_records, total))

        added = self._detect_added(expected_names, incoming_keys, incoming_records, total)
        diffs.extend(added)
        return diffs

    def _detect_removed_and_renamed(
        self,
        expected: ExpectedSchema,
        records: list[dict[str, object]],
        incoming_keys: set[str],
        expected_names: set[str],
        total: int,
    ) -> tuple[list[SchemaDiff], list[SchemaDiff]]:
        """Detect removed fields and possible renames."""
        removed: list[SchemaDiff] = []
        renamed: list[SchemaDiff] = []
        used_new: set[str] = set()

        new_keys = incoming_keys - expected_names - used_new
        for field in expected.fields:
            key_present = sum(1 for r in records if field.field_name in r)
            if key_present == total:
                continue
            if 0 < key_present < total:
                continue
            candidate = _best_rename_candidate(field, new_keys, records)
            if candidate is not None:
                new_name, score = candidate
                used_new.add(new_name)
                confidence = min(1.0, score * (total / total))
                renamed.append(
                    SchemaDiff(
                        diff_type=DiffType.FIELD_RENAMED,
                        field_name=field.field_name,
                        severity="critical",
                        description=(
                            f"Field '{field.field_name}' missing; likely renamed to '{new_name}'"
                        ),
                        old_value=field.field_name,
                        new_value=new_name,
                        affected_records=total,
                        total_records=total,
                        confidence=max(0.9, confidence),
                        suggested_rename=new_name,
                        target_field=field.target_field,
                    )
                )
                continue
            if key_present == 0:
                severity = (
                    "critical"
                    if field.target_field in CRITICAL_REQUIRED_TARGETS
                    else "warning"
                )
                removed.append(
                    SchemaDiff(
                        diff_type=DiffType.FIELD_REMOVED,
                        field_name=field.field_name,
                        severity=severity,
                        description=f"Field '{field.field_name}' absent from all records",
                        old_value=field.field_name,
                        new_value=None,
                        affected_records=total,
                        total_records=total,
                        confidence=1.0,
                        target_field=field.target_field,
                    )
                )
        return removed, renamed

    def _diff_existing_field(
        self,
        field: ExpectedField,
        records: list[dict[str, object]],
        total: int,
    ) -> list[SchemaDiff]:
        """Detect type, format, enum, nullable, and distribution drift."""
        diffs: list[SchemaDiff] = []
        values: list[object] = []
        null_count = 0
        for rec in records:
            val = get_field_value(rec, field.field_name)
            if val is None or val == "":
                null_count += 1
            else:
                values.append(val)

        if null_count > 0 and not field.nullable and null_count < total:
            diffs.append(
                SchemaDiff(
                    diff_type=DiffType.NULLABLE_CHANGED,
                    field_name=field.field_name,
                    severity="warning",
                    description=f"Field '{field.field_name}' now nullable in some records",
                    old_value="non-nullable",
                    new_value="nullable",
                    affected_records=null_count,
                    total_records=total,
                    confidence=null_count / total,
                    target_field=field.target_field,
                )
            )

        if not values:
            return diffs

        sample_strs = {str(s) for s in field.sample_values}
        if sample_strs and all(str(v) in sample_strs for v in values):
            return diffs

        type_diff = _detect_type_change(field, values, total)
        if type_diff:
            diffs.append(type_diff)

        format_diff = _detect_format_change(field, values, total)
        if format_diff:
            diffs.append(format_diff)

        enum_diff = _detect_enum_change(field, values, total)
        if enum_diff:
            diffs.append(enum_diff)

        dist_diff = _detect_distribution_shift(field, values, total)
        if dist_diff:
            diffs.append(dist_diff)

        return diffs

    def _detect_added(
        self,
        expected_names: set[str],
        incoming_keys: set[str],
        records: list[dict[str, object]],
        total: int,
    ) -> list[SchemaDiff]:
        """Detect new fields present in incoming but not expected."""
        diffs: list[SchemaDiff] = []
        for key in sorted(incoming_keys - expected_names):
            present = sum(1 for r in records if get_field_value(r, key) is not None)
            if present < total * PRESENCE_THRESHOLD:
                continue
            diffs.append(
                SchemaDiff(
                    diff_type=DiffType.FIELD_ADDED,
                    field_name=key,
                    severity="info",
                    description=f"New field '{key}' present in incoming data",
                    old_value=None,
                    new_value=key,
                    affected_records=present,
                    total_records=total,
                    confidence=present / total,
                )
            )
        return diffs


def _collect_keys(records: list[dict[str, object]]) -> set[str]:
    """Collect all top-level keys across records."""
    keys: set[str] = set()
    for rec in records:
        keys.update(rec.keys())
    return keys


def _best_rename_candidate(
    field: ExpectedField,
    candidates: set[str],
    records: list[dict[str, object]],
) -> tuple[str, float] | None:
    """Find best rename candidate by name similarity and value overlap."""
    best_name: str | None = None
    best_score = 0.0
    expected_samples = {str(v) for v in field.sample_values}

    total = len(records)
    for name in candidates:
        present = sum(1 for r in records if name in r)
        if present < total * PRESENCE_THRESHOLD:
            continue
        ratio = SequenceMatcher(None, field.field_name.lower(), name.lower()).ratio()
        new_samples = {
            str(get_field_value(r, name))
            for r in records
            if get_field_value(r, name) is not None
        }
        overlap = _jaccard(expected_samples, new_samples) if expected_samples else ratio
        if ratio < RENAME_RATIO_THRESHOLD and overlap < 0.5:
            continue
        score = 0.5 * ratio + 0.5 * overlap
        if score > best_score:
            best_score = score
            best_name = name
    if best_name is None:
        return None
    if best_score < RENAME_RATIO_THRESHOLD and _jaccard(expected_samples, new_samples) < 0.8:
        return None
    return best_name, best_score


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two string sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _detect_type_change(
    field: ExpectedField,
    values: list[object],
    total: int,
) -> SchemaDiff | None:
    """Detect when values are a different type than expected."""
    inferred = [_infer_type(v) for v in values]
    dominant = max(set(inferred), key=inferred.count)
    if dominant == field.expected_type:
        return None
    if field.expected_type in {"string", "date"} and dominant == "string":
        return None
    affected = sum(1 for t in inferred if t == dominant)
    if affected < total * 0.5:
        return None
    return SchemaDiff(
        diff_type=DiffType.TYPE_CHANGED,
        field_name=field.field_name,
        severity="critical",
        description=(
            f"Field '{field.field_name}' type changed from {field.expected_type} to {dominant}"
        ),
        old_value=field.expected_type,
        new_value=dominant,
        affected_records=affected,
        total_records=total,
        confidence=affected / total,
        target_field=field.target_field,
    )


def _detect_format_change(
    field: ExpectedField,
    values: list[object],
    total: int,
) -> SchemaDiff | None:
    """Detect format pattern changes for string-like values."""
    if field.expected_type not in {"string", "date", "datetime"}:
        return None
    formats: list[str | None] = []
    for val in values:
        if not isinstance(val, str):
            formats.append(None)
            continue
        _itype, fmt = detect_string_format(val)
        formats.append(fmt)
    non_null = [f for f in formats if f]
    if not non_null:
        return None
    dominant = max(set(non_null), key=non_null.count)
    if field.expected_format and dominant == field.expected_format:
        return None
    if field.expected_format is None and dominant is None:
        return None
    affected = sum(1 for f in formats if f == dominant)
    if affected < total * 0.8:
        return None
    return SchemaDiff(
        diff_type=DiffType.FORMAT_CHANGED,
        field_name=field.field_name,
        severity="critical",
        description=(
            f"Field '{field.field_name}' format changed from {field.expected_format} to {dominant}"
        ),
        old_value=field.expected_format,
        new_value=dominant,
        affected_records=affected,
        total_records=total,
        confidence=affected / total,
        target_field=field.target_field,
    )


def _detect_enum_change(
    field: ExpectedField,
    values: list[object],
    total: int,
) -> SchemaDiff | None:
    """Detect new enum values not in expected set."""
    if not field.enum_values:
        return None
    expected_set = set(field.enum_values)
    observed = {str(v) for v in values if v is not None}
    new_vals = observed - expected_set
    if not new_vals:
        return None
    affected = sum(1 for v in values if str(v) in new_vals)
    return SchemaDiff(
        diff_type=DiffType.ENUM_VALUE_ADDED,
        field_name=field.field_name,
        severity="warning",
        description=f"New enum value(s) {sorted(new_vals)} in '{field.field_name}'",
        old_value=str(sorted(expected_set)),
        new_value=str(sorted(new_vals)),
        affected_records=affected,
        total_records=total,
        confidence=affected / total,
        target_field=field.target_field,
    )


def _detect_distribution_shift(
    field: ExpectedField,
    values: list[object],
    total: int,
) -> SchemaDiff | None:
    """Detect significant statistical shift in numeric or string length distributions."""
    if field.expected_type in {"integer", "decimal"}:
        nums = [_to_float(v) for v in values]
        nums = [n for n in nums if n is not None]
        if len(nums) < 2:
            return None
        baseline = [_to_float(v) for v in field.sample_values]
        baseline = [n for n in baseline if n is not None]
        if len(baseline) < 2:
            return None
        if statistics.pvariance(baseline) == 0:
            return None
        mean_new = statistics.mean(nums)
        mean_old = statistics.mean(baseline)
        if mean_old == 0:
            return None
        if abs(mean_new - mean_old) / abs(mean_old) < DISTRIBUTION_SHIFT_RATIO:
            return None
        return SchemaDiff(
            diff_type=DiffType.DISTRIBUTION_SHIFTED,
            field_name=field.field_name,
            severity="info",
            description=f"Numeric distribution shifted for '{field.field_name}'",
            old_value=str(mean_old),
            new_value=str(mean_new),
            affected_records=len(nums),
            total_records=total,
            confidence=0.85,
            target_field=field.target_field,
        )
    if field.expected_type == "string":
        lengths = [len(str(v)) for v in values]
        baseline_lengths = [len(s) for s in field.sample_values]
        if len(baseline_lengths) < 2 or not lengths:
            return None
        if statistics.pvariance(baseline_lengths) == 0:
            return None
        mean_new = statistics.mean(lengths)
        mean_old = statistics.mean(baseline_lengths)
        if mean_old == 0:
            return None
        if abs(mean_new - mean_old) / mean_old < DISTRIBUTION_SHIFT_RATIO:
            return None
        return SchemaDiff(
            diff_type=DiffType.DISTRIBUTION_SHIFTED,
            field_name=field.field_name,
            severity="info",
            description=f"String length distribution shifted for '{field.field_name}'",
            old_value=str(mean_old),
            new_value=str(mean_new),
            affected_records=len(lengths),
            total_records=total,
            confidence=0.85,
            target_field=field.target_field,
        )
    return None


def _infer_type(value: object) -> str:
    """Infer type string for a single value."""
    if isinstance(value, str):
        itype, _fmt = detect_string_format(value)
        return itype
    return python_type_to_inferred(value)


def _to_float(value: object) -> float | None:
    """Convert value to float for statistics."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip().isdigit():
        return float(value)
    return None
