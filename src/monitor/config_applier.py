"""Apply ConfigChange entries to a MappingConfig."""

from __future__ import annotations

import copy

from src.exceptions import MonitorError
from src.mapping.config import (
    FieldMapping,
    FieldTransform,
    MappingConfig,
    MatchType,
    TransformType,
)
from src.monitor.codes import MON_APPLY_FAILED
from src.monitor.proposer import ConfigChange, FixType


def apply_config_changes(
    config: MappingConfig,
    changes: list[ConfigChange],
    fix_type: FixType,
) -> MappingConfig:
    """Return a new MappingConfig with changes applied."""
    updated = config.model_copy(deep=True)
    try:
        for change in changes:
            updated = _apply_one(updated, change, fix_type)
    except Exception as exc:
        raise MonitorError(
            MON_APPLY_FAILED,
            f"Failed to apply config changes: {exc}",
        ) from exc
    return updated


def _apply_one(
    config: MappingConfig,
    change: ConfigChange,
    fix_type: FixType,
) -> MappingConfig:
    """Apply a single config change."""
    ctype = change.change_type
    if ctype == "update_field_mapping" or fix_type == FixType.UPDATE_FIELD_NAME:
        return _update_field_name(config, change)
    if ctype == "update_transform" or fix_type == FixType.UPDATE_TRANSFORM:
        return _update_transform(config, change)
    if ctype == "add_field_mapping" or fix_type == FixType.ADD_MAPPING:
        return _add_mapping(config, change)
    if ctype == "remove_field_mapping" or fix_type == FixType.REMOVE_MAPPING:
        return _remove_mapping(config, change)
    if ctype == "update_enum_map" or fix_type == FixType.UPDATE_ENUM_MAP:
        return _update_enum_map(config, change)
    return config


def _update_field_name(config: MappingConfig, change: ConfigChange) -> MappingConfig:
    """Rename source_field on an existing mapping."""
    mappings: list[FieldMapping] = []
    for m in config.field_mappings:
        if m.source_field == change.field_path or m.source_field == change.old_value:
            mappings.append(
                m.model_copy(update={"source_field": change.new_value or change.field_path})
            )
        else:
            mappings.append(m)
    return config.model_copy(update={"field_mappings": mappings})


def _update_transform(config: MappingConfig, change: ConfigChange) -> MappingConfig:
    """Update transform parameters on a mapping."""
    mappings: list[FieldMapping] = []
    for m in config.field_mappings:
        if m.source_field != change.field_path:
            mappings.append(m)
            continue
        transform = m.transform or FieldTransform(
            transform_type=TransformType.DATE_FORMAT,
            source_format=change.old_value,
            target_format=change.new_value,
        )
        if m.transform:
            transform = m.transform.model_copy(
                update={
                    "source_format": change.new_value or change.old_value,
                    "target_format": m.transform.target_format,
                }
            )
        mappings.append(m.model_copy(update={"transform": transform}))
    return config.model_copy(update={"field_mappings": mappings})


def _add_mapping(config: MappingConfig, change: ConfigChange) -> MappingConfig:
    """Append a new field mapping."""
    new_mapping = FieldMapping(
        source_field=change.field_path,
        target_field=change.new_value or "claim.raw_data",
        match_type=MatchType.MANUAL,
        confidence=0.5,
        reasoning=change.explanation,
    )
    return config.model_copy(
        update={"field_mappings": [*config.field_mappings, new_mapping]}
    )


def _remove_mapping(config: MappingConfig, change: ConfigChange) -> MappingConfig:
    """Remove mapping by source field."""
    kept = [m for m in config.field_mappings if m.source_field != change.field_path]
    return config.model_copy(update={"field_mappings": kept})


def _update_enum_map(config: MappingConfig, change: ConfigChange) -> MappingConfig:
    """Merge enum values into transform parameters."""
    mappings: list[FieldMapping] = []
    for m in config.field_mappings:
        if m.source_field != change.field_path:
            mappings.append(m)
            continue
        params = copy.deepcopy(m.transform.parameters if m.transform else {}) or {}
        raw_enum = params.get("enum_map")
        enum_map = dict(raw_enum) if isinstance(raw_enum, dict) else {}
        if change.new_value:
            enum_map[change.new_value] = change.new_value
        transform = (m.transform or FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={"enum_map": {}},
        )).model_copy(update={"parameters": {"enum_map": enum_map}})
        mappings.append(m.model_copy(update={"transform": transform}))
    return config.model_copy(update={"field_mappings": mappings})
