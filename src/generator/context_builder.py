"""Build Jinja2 template context from MappingConfig."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from src.generator.name_utils import sanitize_client_name
from src.generator.schema_introspector import SchemaIntrospector
from src.mapping.config import (
    FieldMapping,
    FieldTransform,
    MappingConfig,
    TransformType,
    collect_unique_transforms,
)

STRPTIME_FORMATS: dict[str, str] = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "ISO 8601": "%Y-%m-%dT%H:%M:%S",
    "YYYYMMDD": "%Y%m%d",
    "YYYY/MM/DD": "%Y/%m/%d",
    "M/D/YYYY": "%m/%d/%Y",
}


def _slug(value: str) -> str:
    """Convert a label to a stable snake identifier fragment."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_") or "default"


def _transform_key(transform: FieldTransform) -> tuple[object, ...]:
    """Hashable key for deduplicating transform methods."""
    params = transform.parameters or {}
    param_items = tuple(sorted((str(k), repr(v)) for k, v in params.items()))
    return (
        transform.transform_type,
        transform.source_format,
        transform.target_format,
        param_items,
    )


def _method_name_for_transform(transform: FieldTransform) -> str:
    """Assign a stable Python method name for a transform."""
    match transform.transform_type:
        case TransformType.DATE_FORMAT:
            label = transform.source_format or "date"
            return f"_transform_date_{_slug(label)}"
        case TransformType.CURRENCY_PARSE:
            return "_transform_currency"
        case TransformType.BOOLEAN_PARSE:
            return "_transform_boolean"
        case TransformType.ENUM_MAP:
            params = transform.parameters or {}
            enum_name = str(params.get("enum_name", "enum"))
            return f"_transform_enum_{_slug(enum_name)}"
        case TransformType.TYPE_CAST:
            target = transform.target_format or "str"
            return f"_transform_type_cast_{_slug(target)}"
        case TransformType.SPLIT_FIELD:
            params = transform.parameters or {}
            field = str(params.get("field_id", params.get("source_field", "split")))
            return f"_transform_split_{_slug(field)}"
        case TransformType.MERGE_FIELDS:
            params = transform.parameters or {}
            target = str(params.get("target_field", "merge"))
            return f"_transform_merge_{_slug(target)}"
        case TransformType.STRING_NORMALIZE:
            return "_transform_string_normalize"
        case TransformType.CUSTOM:
            return "_transform_custom"
        case _:
            return "_transform_unknown"


def _transform_render_context(
    transform: FieldTransform,
    method_name: str,
    introspector: SchemaIntrospector,
) -> dict[str, Any]:
    """Build partial-template context for one deduped transform."""
    ctx: dict[str, Any] = {
        "transform_type": transform.transform_type.value,
        "method_name": method_name,
    }
    params = transform.parameters or {}
    match transform.transform_type:
        case TransformType.DATE_FORMAT:
            label = transform.source_format or "YYYY-MM-DD"
            ctx["strptime_format"] = STRPTIME_FORMATS.get(label, "%Y-%m-%d")
        case TransformType.BOOLEAN_PARSE:
            ctx["true_values"] = [
                str(v).lower()
                for v in (params.get("true_values") or ["true", "yes", "y", "1", "t"])
            ]
            ctx["false_values"] = [
                str(v).lower()
                for v in (params.get("false_values") or ["false", "no", "n", "0", "f"])
            ]
        case TransformType.ENUM_MAP:
            enum_name = str(params.get("enum_name", "enum"))
            ctx["enum_name"] = enum_name
            ctx["enum_map"] = dict(params.get("enum_map") or {})
            target_path = str(params.get("target_field", f"claim.{enum_name.lower()}"))
            spec = introspector.get_all_fields().get(target_path)
            ctx["target_enum_values"] = list(spec.enum_values or []) if spec else []
        case TransformType.TYPE_CAST:
            target = transform.target_format or "Decimal"
            ctx["target_type"] = target
            ctx["return_annotation"] = target if target != "float" else "Decimal"
        case TransformType.SPLIT_FIELD:
            targets = list(params.get("targets") or [])
            ctx["targets"] = targets
            ctx["delimiter"] = str(params.get("delimiter", ","))
            ctx["maxsplit"] = max(0, len(targets) - 1) if targets else 0
            ctx["field_id"] = str(params.get("field_id", "field"))
        case TransformType.MERGE_FIELDS:
            source_fields = list(params.get("source_fields") or [])
            ctx["source_fields"] = source_fields
            ctx["target_field"] = str(params.get("target_field", "claim.loss_location"))
            field_map = dict(params.get("field_map") or {})
            if not field_map and source_fields:
                field_map = {
                    _slug(f): f for f in source_fields
                }
            ctx["field_map"] = field_map
        case _:
            pass
    return ctx


def build_template_context(
    config: MappingConfig,
    *,
    timestamp: datetime | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Prepare Jinja context for adapter and test templates."""
    introspector = SchemaIntrospector()
    class_name, module_name, file_stem, display_name = sanitize_client_name(config.client_name)
    gen_warnings = list(warnings or [])

    field_mappings: dict[str, str] = {}
    mapping_rows: list[dict[str, str | None]] = []
    transforms_by_source: dict[str, str] = {}

    seen_targets: dict[str, str] = {}
    for mapping in config.field_mappings:
        if mapping.target_field.startswith("policy_snapshot."):
            gen_warnings.append(
                f"Skipping policy_snapshot mapping for {mapping.source_field}",
            )
            continue
        if mapping.target_field in seen_targets:
            gen_warnings.append(
                f"Duplicate target {mapping.target_field}; last mapping wins",
            )
        seen_targets[mapping.target_field] = mapping.source_field
        field_mappings[mapping.source_field] = mapping.target_field
        mapping_rows.append(
            {
                "source_field": mapping.source_field,
                "source_path": mapping.source_path,
                "target_field": mapping.target_field,
            },
        )

    all_transforms = collect_unique_transforms(config.field_mappings)
    for extra in config.transforms:
        if extra not in all_transforms:
            all_transforms.append(extra)

    method_by_key: dict[tuple[object, ...], str] = {}
    needed_transforms: list[dict[str, Any]] = []
    for transform in all_transforms:
        key = _transform_key(transform)
        if key not in method_by_key:
            method_name = _method_name_for_transform(transform)
            method_by_key[key] = method_name
            needed_transforms.append(
                _transform_render_context(transform, method_name, introspector),
            )

    for mapping in config.field_mappings:
        if mapping.transform is None:
            continue
        key = _transform_key(mapping.transform)
        method_name = method_by_key[key]
        transforms_by_source[mapping.source_field] = method_name

    enum_imports: set[str] = set()
    enum_maps: dict[str, dict[str, str]] = {}
    for row in config.field_mappings:
        spec = introspector.get_all_fields().get(row.target_field)
        if spec and spec.is_enum and spec.python_type:
            enum_imports.add(spec.python_type)
            if row.transform and row.transform.parameters:
                raw_map = row.transform.parameters.get("enum_map")
                if isinstance(raw_map, dict):
                    enum_maps[row.target_field] = {
                        str(k): str(v) for k, v in raw_map.items()
                    }

    sample_records = _build_sample_records(config.field_mappings)

    return {
        "client_name": display_name,
        "class_name": class_name,
        "module_name": module_name,
        "file_stem": file_stem,
        "source_format": config.source_format,
        "timestamp": (timestamp or config.created_at).isoformat(),
        "field_mappings": field_mappings,
        "mapping_rows": mapping_rows,
        "transforms_by_source": transforms_by_source,
        "needed_transforms": needed_transforms,
        "enum_imports": sorted(enum_imports),
        "enum_maps": enum_maps,
        "sample_records": sample_records,
        "schema_version": config.schema_version,
        "warnings": gen_warnings,
    }


def _build_sample_records(mappings: list[FieldMapping]) -> list[dict[str, object]]:
    """Build minimal sample raw records for generated tests."""
    record: dict[str, object] = {}
    for mapping in mappings:
        if mapping.source_field not in record:
            record[mapping.source_field] = _sample_value_for_mapping(mapping)
    return [record]


def _sample_value_for_mapping(mapping: FieldMapping) -> object:
    """Infer a sample source value from mapping metadata."""
    if mapping.transform:
        match mapping.transform.transform_type:
            case TransformType.DATE_FORMAT:
                return "2024-01-15"
            case TransformType.CURRENCY_PARSE:
                return "$1,234.56"
            case TransformType.BOOLEAN_PARSE:
                return "Y"
            case TransformType.SPLIT_FIELD:
                return "Doe, John"
            case _:
                pass
    if "date" in mapping.source_field.lower():
        return "2024-01-15"
    if "amount" in mapping.source_field.lower() or "paid" in mapping.source_field.lower():
        return "100.00"
    return f"sample_{mapping.source_field}"
