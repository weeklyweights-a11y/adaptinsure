"""Universal schema field introspection for the Adapter Code Generator."""

from __future__ import annotations

import types
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from src.schema.models import (
    Claim,
    Claimant,
    Exposure,
    PolicySnapshot,
    Transaction,
)

_TOP_LEVEL_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("claim", Claim),
    ("exposure", Exposure),
    ("claimant", Claimant),
    ("transaction", Transaction),
    ("policy_snapshot", PolicySnapshot),
)


class FieldSpec(BaseModel):
    """Describes one field on the universal schema."""

    model_config = ConfigDict(strict=True)

    path: Annotated[str, Field(description="Dot-path field name")]
    python_type: Annotated[str, Field(description="Python type as string")]
    is_required: Annotated[bool, Field(description="Required on parent model")]
    is_list: Annotated[bool, Field(default=False)]
    is_enum: Annotated[bool, Field(default=False)]
    enum_values: Annotated[list[str] | None, Field(default=None)]
    parent_entity: Annotated[str, Field(description="Top-level entity prefix")]


def _unwrap(annotation: Any) -> Any:
    """Unwrap Optional and Annotated types."""
    origin = get_origin(annotation)
    if origin is list or origin is dict:
        return annotation
    if origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else annotation
    if origin is not None:
        args = get_args(annotation)
        if args:
            return args[0]
    return annotation


def _is_optional(annotation: Any) -> bool:
    """Return True if the annotation allows None."""
    origin = get_origin(annotation)
    if origin is types.UnionType:
        return type(None) in get_args(annotation)
    return False


def _type_label(annotation: Any) -> str:
    """Map a field annotation to a simple type name string."""
    inner = _unwrap(annotation)
    if isinstance(inner, type) and issubclass(inner, Enum):
        return inner.__name__
    if inner is str:
        return "str"
    if inner is int:
        return "int"
    if inner is bool:
        return "bool"
    if inner is Decimal:
        return "Decimal"
    if inner is datetime:
        return "datetime"
    if inner is date:
        return "date"
    if isinstance(inner, type) and issubclass(inner, BaseModel):
        return inner.__name__
    if get_origin(inner) is list:
        args = get_args(inner)
        if args:
            return f"list[{_type_label(args[0])}]"
        return "list"
    if get_origin(inner) is dict:
        return "dict"
    return getattr(inner, "__name__", str(inner))


def _field_required(field_info: Any) -> bool:
    """True when the field has no default and is not optional."""
    if _is_optional(field_info.annotation):
        return False
    return field_info.is_required()


def _walk_model(
    model: type[BaseModel],
    prefix: str,
    parent_entity: str,
) -> dict[str, FieldSpec]:
    """Recursively collect FieldSpec entries."""
    fields: dict[str, FieldSpec] = {}
    for name, field_info in model.model_fields.items():
        path = f"{prefix}.{name}"
        annotation = field_info.annotation
        inner = _unwrap(annotation)
        origin = get_origin(inner)
        if origin is list:
            inner_type = get_args(inner)[0] if get_args(inner) else Any
            enum_vals = None
            is_enum = False
            unwrapped = _unwrap(inner_type)
            if isinstance(unwrapped, type) and issubclass(unwrapped, Enum):
                is_enum = True
                enum_vals = [m.value for m in unwrapped]
            fields[path] = FieldSpec(
                path=path,
                python_type=_type_label(annotation),
                is_required=_field_required(field_info),
                is_list=True,
                is_enum=is_enum,
                enum_values=enum_vals,
                parent_entity=parent_entity,
            )
            continue
        if origin is dict:
            fields[path] = FieldSpec(
                path=path,
                python_type=_type_label(annotation),
                is_required=_field_required(field_info),
                is_list=False,
                is_enum=False,
                enum_values=None,
                parent_entity=parent_entity,
            )
            continue
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            fields.update(_walk_model(inner, path, parent_entity))
            continue
        is_enum = isinstance(inner, type) and issubclass(inner, Enum)
        enum_vals = [m.value for m in inner] if is_enum else None
        fields[path] = FieldSpec(
            path=path,
            python_type=_type_label(annotation),
            is_required=_field_required(field_info),
            is_list=False,
            is_enum=is_enum,
            enum_values=enum_vals,
            parent_entity=parent_entity,
        )
    return fields


class SchemaIntrospector:
    """Extract field metadata from universal schema Pydantic models."""

    def get_all_fields(self) -> dict[str, FieldSpec]:
        """Return all schema field paths and their specifications."""
        result: dict[str, FieldSpec] = {}
        for prefix, model in _TOP_LEVEL_MODELS:
            result.update(_walk_model(model, prefix, prefix.split(".")[0]))
        return result

    def get_required_fields(self) -> list[str]:
        """Return dot-path names of required fields."""
        return [path for path, spec in self.get_all_fields().items() if spec.is_required]

    def get_entity_names(self) -> list[str]:
        """Return top-level entity names."""
        return [prefix for prefix, _ in _TOP_LEVEL_MODELS]
