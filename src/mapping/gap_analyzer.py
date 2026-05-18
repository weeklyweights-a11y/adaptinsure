"""Identify mapping gaps for missing, unmapped, and low-confidence fields."""

from __future__ import annotations

from src.discovery.profile import FieldInfo
from src.mapping.config import FieldMapping, GapInfo, GapType
from src.mapping.schema_registry import (
    CRITICAL_REQUIRED_TARGETS,
    get_optional_schema_fields,
)

_LOW_CONFIDENCE_SUGGESTION = (
    "This mapping has low confidence. Please review and confirm or correct."
)
_MISSING_REQUIRED_SUGGESTION = (
    "This field is required. Check if the source data has an equivalent field "
    "under a different name, or provide a default value."
)
_UNMAPPED_SOURCE_SUGGESTION = (
    "This source field has no equivalent in the universal schema. "
    "It will be preserved in raw_data."
)


def _source_key(field: FieldInfo) -> str:
    return field.nesting_path or field.source_name


class GapAnalyzer:
    """Analyze mappings and source fields to produce gap reports."""

    def analyze(
        self,
        mappings: list[FieldMapping],
        source_fields: list[FieldInfo],
        mapped_sources: set[str],
        *,
        semantic_gap_fields: set[str] | None = None,
        ambiguous_sources: set[str] | None = None,
    ) -> list[GapInfo]:
        """Run all gap checks and return deduplicated gap list."""
        gaps: list[GapInfo] = []
        mapped_targets = {m.target_field for m in mappings}
        semantic_gap_fields = semantic_gap_fields or set()
        ambiguous_sources = ambiguous_sources or set()

        for target in sorted(CRITICAL_REQUIRED_TARGETS - mapped_targets):
            if target == "claim.loss_location":
                if any(t.startswith("claim.loss_location") for t in mapped_targets):
                    continue
            gaps.append(
                GapInfo(
                    field_name=target,
                    gap_type=GapType.MISSING_REQUIRED,
                    severity="critical",
                    description=f"Required universal field {target} is not mapped",
                    suggestion=_MISSING_REQUIRED_SUGGESTION,
                )
            )

        for target in sorted(get_optional_schema_fields() - mapped_targets):
            gaps.append(
                GapInfo(
                    field_name=target,
                    gap_type=GapType.MISSING_OPTIONAL,
                    severity="info",
                    description=f"Optional universal field {target} is not mapped",
                )
            )

        for field in source_fields:
            key = _source_key(field)
            if key in mapped_sources or field.source_name in semantic_gap_fields:
                continue
            gaps.append(
                GapInfo(
                    field_name=field.source_name,
                    gap_type=GapType.UNMAPPED_SOURCE,
                    severity="warning",
                    description=f"Source field {field.source_name} has no mapping",
                    suggestion=_UNMAPPED_SOURCE_SUGGESTION,
                )
            )

        for mapping in mappings:
            if mapping.confidence < 0.5:
                gaps.append(
                    GapInfo(
                        field_name=mapping.source_field,
                        gap_type=GapType.AMBIGUOUS,
                        severity="warning",
                        description=f"Low confidence mapping for {mapping.source_field}",
                        suggestion=_LOW_CONFIDENCE_SUGGESTION,
                    )
                )

        for source_name in sorted(ambiguous_sources):
            gaps.append(
                GapInfo(
                    field_name=source_name,
                    gap_type=GapType.AMBIGUOUS,
                    severity="warning",
                    description=f"Field {source_name} could map to multiple targets",
                    suggestion=_LOW_CONFIDENCE_SUGGESTION,
                )
            )

        return _dedupe_gaps(gaps)


def _dedupe_gaps(gaps: list[GapInfo]) -> list[GapInfo]:
    """Remove duplicate gaps by field_name and gap_type."""
    seen: set[tuple[str, str]] = set()
    result: list[GapInfo] = []
    for gap in gaps:
        key = (gap.field_name, gap.gap_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(gap)
    return result
