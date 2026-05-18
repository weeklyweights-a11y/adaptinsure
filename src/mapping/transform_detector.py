"""Detect format transforms needed for field mappings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.discovery.profile import FieldInfo
from src.mapping.config import (
    FieldMapping,
    FieldTransform,
    GapInfo,
    GapType,
    MatchType,
    TransformType,
)
from src.mapping.schema_registry import get_universal_schema_fields

_DATE_PATTERNS: list[tuple[str, str]] = [
    ("ISO 8601", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
    ("YYYY-MM-DD", r"^\d{4}-\d{2}-\d{2}$"),
    ("MM/DD/YYYY", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    ("DD/MM/YYYY", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    ("M/D/YYYY", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    ("YYYYMMDD", r"^\d{8}$"),
    ("MM-DD-YYYY", r"^\d{1,2}-\d{1,2}-\d{4}$"),
    ("DD-MMM-YYYY", r"^\d{2}-[A-Za-z]{3}-\d{4}$"),
]

_CURRENCY_RE = re.compile(r"^(?:\$\d[\d,]*\.\d{2}|\d{1,3}(?:,\d{3})+\.\d{2})$")
_BOOL_YN = frozenset({"Y", "N", "y", "n"})
_BOOL_TRUE_FALSE = frozenset({"true", "false", "True", "False"})


@dataclass(frozen=True)
class TransformResult:
    """Updated mappings and optional format gaps from transform detection."""

    mappings: list[FieldMapping]
    gaps: list[GapInfo]


def _field_key(field: FieldInfo) -> str:
    return field.nesting_path or field.source_name


def _detect_date_format(samples: list[str]) -> tuple[str | None, bool]:
    """Detect date format from samples; return (format, ambiguous)."""
    if not samples:
        return None, False
    matched: list[str] = []
    for label, pattern in _DATE_PATTERNS:
        if all(re.match(pattern, s.strip()) for s in samples):
            matched.append(label)
    if not matched:
        return None, False
    if len(matched) > 1 and "MM/DD/YYYY" in matched and "DD/MM/YYYY" in matched:
        return matched[0], True
    return matched[0], len(matched) > 1


class TransformDetector:
    """Enrich mappings with transform metadata based on source/target types."""

    def __init__(self) -> None:
        """Initialize with universal schema type map."""
        self._target_types = get_universal_schema_fields()

    def detect_transforms(
        self,
        mappings: list[FieldMapping],
        source_fields: list[FieldInfo],
    ) -> TransformResult:
        """Return mappings with transforms populated where needed."""
        by_key = {_field_key(f): f for f in source_fields}
        updated: list[FieldMapping] = []
        gaps: list[GapInfo] = []
        for mapping in mappings:
            info = by_key.get(mapping.source_field) or by_key.get(
                mapping.source_path or ""
            )
            if info is None:
                updated.append(mapping)
                continue
            target_type = self._target_types.get(mapping.target_field, "")
            new_mapping, extra_gaps = self._detect_one(mapping, info, target_type)
            updated.extend(new_mapping)
            gaps.extend(extra_gaps)
        return TransformResult(mappings=updated, gaps=gaps)

    def _detect_one(
        self,
        mapping: FieldMapping,
        info: FieldInfo,
        target_type: str,
    ) -> tuple[list[FieldMapping], list[GapInfo]]:
        """Detect transform for a single mapping; may split into multiple rows."""
        gaps: list[GapInfo] = []
        samples = info.sample_values
        src_type = info.inferred_type

        if mapping.source_field.lower() in {"full_name", "fullname"} and any(
            t in mapping.target_field for t in ("first_name", "last_name")
        ):
            transform = FieldTransform(
                transform_type=TransformType.SPLIT_FIELD,
                parameters={"targets": ["claimant.first_name", "claimant.last_name"]},
            )
            return [
                FieldMapping(
                    source_field=mapping.source_field,
                    source_path=mapping.source_path,
                    target_field="claimant.first_name",
                    match_type=MatchType.COMPUTED,
                    confidence=mapping.confidence,
                    reasoning=f"{mapping.reasoning}; split to first_name",
                    transform=transform,
                ),
                FieldMapping(
                    source_field=mapping.source_field,
                    source_path=mapping.source_path,
                    target_field="claimant.last_name",
                    match_type=MatchType.COMPUTED,
                    confidence=mapping.confidence,
                    reasoning=f"{mapping.reasoning}; split to last_name",
                    transform=transform,
                ),
            ], gaps

        if mapping.transform is not None:
            return [mapping], gaps

        transform: FieldTransform | None = None
        confidence = mapping.confidence
        reasoning = mapping.reasoning

        if target_type == "datetime" and src_type in {"string", "date"}:
            fmt, ambiguous = _detect_date_format(samples)
            if fmt:
                transform = FieldTransform(
                    transform_type=TransformType.DATE_FORMAT,
                    source_format=fmt,
                    target_format="ISO 8601",
                )
                if ambiguous:
                    confidence = min(confidence, 0.45)
                    reasoning = f"{reasoning}; ambiguous date format (MM/DD vs DD/MM)"
                    gaps.append(
                        GapInfo(
                            field_name=mapping.source_field,
                            gap_type=GapType.FORMAT_UNKNOWN,
                            severity="warning",
                            description="Date format could be MM/DD or DD/MM",
                        )
                    )
            elif samples:
                gaps.append(
                    GapInfo(
                        field_name=mapping.source_field,
                        gap_type=GapType.FORMAT_UNKNOWN,
                        severity="warning",
                        description="Could not detect date format from samples",
                    )
                )

        elif target_type == "Decimal":
            if samples and all(_CURRENCY_RE.match(s.strip()) for s in samples):
                transform = FieldTransform(
                    transform_type=TransformType.CURRENCY_PARSE,
                    source_format="$#,###.##",
                    target_format="Decimal",
                )
            elif src_type == "string":
                transform = FieldTransform(
                    transform_type=TransformType.TYPE_CAST,
                    target_format="Decimal",
                )

        elif target_type == "bool" and src_type == "string":
            if samples and all(s in _BOOL_YN for s in samples):
                transform = FieldTransform(
                    transform_type=TransformType.BOOLEAN_PARSE,
                    parameters={"true_values": ["Y"], "false_values": ["N"]},
                )
            elif samples and all(s.lower() in _BOOL_TRUE_FALSE for s in samples):
                transform = FieldTransform(
                    transform_type=TransformType.BOOLEAN_PARSE,
                    parameters={"true_values": ["true"], "false_values": ["false"]},
                )

        elif target_type in {"ClaimStatus", "ExposureStatus", "TransactionStatus"}:
            if samples:
                transform = FieldTransform(
                    transform_type=TransformType.ENUM_MAP,
                    parameters={"sample_values": list(samples)},
                )

        elif target_type == "int" and src_type == "string":
            transform = FieldTransform(
                transform_type=TransformType.TYPE_CAST,
                target_format="int",
            )

        if transform is None:
            return [mapping], gaps

        return [
            mapping.model_copy(
                update={
                    "transform": transform,
                    "confidence": confidence,
                    "reasoning": reasoning,
                }
            )
        ], gaps
