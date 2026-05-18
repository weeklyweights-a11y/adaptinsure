"""Mapping configuration models for the Mapping Engine."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["critical", "warning", "info"]


class MatchType(StrEnum):
    """How a source field was matched to the universal schema."""

    DIRECT = "direct"
    SEMANTIC = "semantic"
    COMPUTED = "computed"
    MANUAL = "manual"


class TransformType(StrEnum):
    """Kind of value conversion between source and target."""

    DATE_FORMAT = "date_format"
    CURRENCY_PARSE = "currency_parse"
    ENUM_MAP = "enum_map"
    STRING_NORMALIZE = "string_normalize"
    BOOLEAN_PARSE = "boolean_parse"
    SPLIT_FIELD = "split_field"
    MERGE_FIELDS = "merge_fields"
    TYPE_CAST = "type_cast"
    CUSTOM = "custom"


class GapType(StrEnum):
    """Category of mapping gap."""

    MISSING_REQUIRED = "missing_required"
    MISSING_OPTIONAL = "missing_optional"
    UNMAPPED_SOURCE = "unmapped_source"
    AMBIGUOUS = "ambiguous"
    FORMAT_UNKNOWN = "format_unknown"


class FieldTransform(BaseModel):
    """Describes a value conversion for a mapped field."""

    model_config = ConfigDict(strict=True)

    transform_type: Annotated[TransformType, Field(description="Transform kind")]
    source_format: Annotated[str | None, Field(default=None)]
    target_format: Annotated[str | None, Field(default=None)]
    parameters: Annotated[dict[str, object] | None, Field(default=None)]


class FieldMapping(BaseModel):
    """Maps one client field to one universal schema field."""

    model_config = ConfigDict(strict=True)

    source_field: Annotated[str, Field(description="Client field name")]
    source_path: Annotated[str | None, Field(default=None)]
    target_field: Annotated[str, Field(description="Universal schema path")]
    match_type: Annotated[MatchType, Field(description="Match classification")]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(min_length=1)]
    transform: Annotated[FieldTransform | None, Field(default=None)]


class GapInfo(BaseModel):
    """Describes a field that does not map cleanly."""

    model_config = ConfigDict(strict=True)

    field_name: Annotated[str, Field(description="Field in question")]
    gap_type: Annotated[GapType, Field(description="Gap category")]
    severity: Annotated[Severity, Field(description="Gap severity")]
    description: Annotated[str, Field(description="Human-readable explanation")]
    suggestion: Annotated[str | None, Field(default=None)]


class ConfidenceSummary(BaseModel):
    """Aggregate confidence statistics for a mapping run."""

    model_config = ConfigDict(strict=True)

    total_fields: Annotated[int, Field(ge=0)]
    mapped_fields: Annotated[int, Field(ge=0)]
    unmapped_fields: Annotated[int, Field(ge=0)]
    high_confidence_count: Annotated[int, Field(ge=0)]
    medium_confidence_count: Annotated[int, Field(ge=0)]
    low_confidence_count: Annotated[int, Field(ge=0)]
    average_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    requires_review: Annotated[bool, Field(default=False)]

    @model_validator(mode="after")
    def compute_requires_review(self) -> ConfidenceSummary:
        """Set requires_review when low-confidence mappings exist."""
        if self.low_confidence_count > 0:
            self.requires_review = True
        return self


class MappingConfig(BaseModel):
    """Complete mapping specification for a client."""

    model_config = ConfigDict(strict=True)

    client_name: Annotated[str, Field(description="Client identifier")]
    source_format: Annotated[str, Field(description="json, xml, or csv")]
    schema_version: Annotated[str, Field(description="Universal schema version")]
    field_mappings: Annotated[list[FieldMapping], Field(default_factory=list)]
    transforms: Annotated[list[FieldTransform], Field(default_factory=list)]
    gaps: Annotated[list[GapInfo], Field(default_factory=list)]
    confidence_summary: Annotated[ConfidenceSummary, Field(description="Aggregate stats")]
    created_at: Annotated[datetime, Field(description="Creation time UTC")]
    notes: Annotated[list[str], Field(default_factory=list)]


def _transform_key(transform: FieldTransform) -> tuple[object, ...]:
    """Build a hashable key for deduplicating transforms."""
    params = transform.parameters or {}
    param_items = tuple(sorted((str(k), repr(v)) for k, v in params.items()))
    return (
        transform.transform_type,
        transform.source_format,
        transform.target_format,
        param_items,
    )


def collect_unique_transforms(mappings: list[FieldMapping]) -> list[FieldTransform]:
    """Collect deduplicated transforms referenced on field mappings."""
    seen: set[tuple[object, ...]] = set()
    result: list[FieldTransform] = []
    for mapping in mappings:
        if mapping.transform is None:
            continue
        key = _transform_key(mapping.transform)
        if key not in seen:
            seen.add(key)
            result.append(mapping.transform)
    return result
