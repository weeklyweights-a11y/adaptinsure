"""Expected schema models for drift monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.discovery.profile import ClientProfile, FieldInfo
from src.mapping.config import FieldMapping, MappingConfig, TransformType


class ExpectedField(BaseModel):
    """What one source field should look like in incoming data."""

    model_config = ConfigDict(strict=True)

    field_name: Annotated[str, Field(description="Source field name")]
    field_path: Annotated[str | None, Field(default=None)]
    target_field: Annotated[str, Field(description="Universal schema path")]
    transform_type: Annotated[str | None, Field(default=None)]
    expected_type: Annotated[str, Field(description="Inferred type")]
    expected_format: Annotated[str | None, Field(default=None)]
    required: Annotated[bool, Field(default=False)]
    sample_values: Annotated[list[str], Field(default_factory=list)]
    enum_values: Annotated[list[str] | None, Field(default=None)]
    nullable: Annotated[bool, Field(default=True)]


class ExpectedSchema(BaseModel):
    """Baseline schema the monitor expects for a deployed adapter."""

    model_config = ConfigDict(strict=True)

    client_name: Annotated[str, Field(description="Client identifier")]
    source_format: Annotated[str, Field(description="json, xml, or csv")]
    fields: Annotated[list[ExpectedField], Field(default_factory=list)]
    created_at: Annotated[datetime, Field(description="Baseline creation UTC")]
    last_validated_at: Annotated[datetime, Field(description="Last clean check UTC")]
    record_count_baseline: Annotated[int, Field(ge=0, description="Records at baseline")]

    @classmethod
    def from_mapping_config(
        cls,
        config: MappingConfig,
        profile: ClientProfile,
    ) -> ExpectedSchema:
        """Build expected schema from mapping config and discovery profile."""
        now = datetime.now(UTC)
        fields: list[ExpectedField] = []
        for mapping in config.field_mappings:
            info = _find_field_info(profile, mapping)
            fields.append(_build_expected_field(mapping, info))
        return cls(
            client_name=config.client_name,
            source_format=config.source_format,
            fields=fields,
            created_at=now,
            last_validated_at=now,
            record_count_baseline=profile.total_records_sampled,
        )


def refresh_expected_schema(
    schema: ExpectedSchema,
    config: MappingConfig,
    profile: ClientProfile,
    *,
    record_count: int | None = None,
) -> ExpectedSchema:
    """Rebuild expected fields from updated mapping config."""
    rebuilt = ExpectedSchema.from_mapping_config(config, profile)
    count = record_count if record_count is not None else schema.record_count_baseline
    return rebuilt.model_copy(
        update={
            "created_at": schema.created_at,
            "record_count_baseline": count,
        }
    )


def _find_field_info(profile: ClientProfile, mapping: FieldMapping) -> FieldInfo | None:
    """Match FieldInfo to a FieldMapping by source name and path."""
    exact: FieldInfo | None = None
    fallback: FieldInfo | None = None
    for info in profile.fields:
        if info.source_name != mapping.source_field:
            continue
        fallback = info
        if mapping.source_path is None:
            if info.nesting_path is None:
                exact = info
                break
        elif info.nesting_path == mapping.source_path:
            exact = info
            break
    return exact or fallback


def _build_expected_field(
    mapping: FieldMapping,
    info: FieldInfo | None,
) -> ExpectedField:
    """Create ExpectedField from mapping and optional FieldInfo."""
    transform = mapping.transform
    transform_type = (
        transform.transform_type.value if transform is not None else None
    )
    expected_format: str | None = None
    enum_values: list[str] | None = None
    if transform is not None:
        expected_format = transform.source_format or transform.target_format
        if transform.transform_type == TransformType.ENUM_MAP and transform.parameters:
            raw_map = transform.parameters.get("enum_map")
            if isinstance(raw_map, dict):
                enum_values = [str(v) for v in raw_map.values()]
    inferred_type = info.inferred_type if info else "string"
    if info and info.format_pattern and expected_format is None:
        expected_format = info.format_pattern
    nullable = info.nullable if info else True
    required = not nullable if info else False
    samples = list(info.sample_values[:5]) if info else []
    return ExpectedField(
        field_name=mapping.source_field,
        field_path=mapping.source_path,
        target_field=mapping.target_field,
        transform_type=transform_type,
        expected_type=inferred_type,
        expected_format=expected_format,
        required=required,
        sample_values=samples,
        enum_values=enum_values,
        nullable=nullable,
    )


def default_schema_path(client_name: str, base_dir: Path | None = None) -> Path:
    """Return default path for persisted expected schema JSON."""
    root = base_dir or Path("data/schemas")
    safe = client_name.replace("/", "_").replace("\\", "_")
    return root / f"{safe}.json"
