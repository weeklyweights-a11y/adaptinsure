"""Universal schema field registry for the Mapping Engine."""

from __future__ import annotations

import types
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from src.schema.models import (
    Claim,
    Claimant,
    Exposure,
    PolicySnapshot,
    Transaction,
)

SCHEMA_VERSION = "1.0.0"

CRITICAL_REQUIRED_TARGETS: frozenset[str] = frozenset(
    {
        "claim.claim_id",
        "claim.claim_number",
        "claim.status",
        "claim.loss_date",
        "claim.reported_date",
        "claim.loss_description",
        "claim.loss_cause",
        "claim.loss_location",
        "claim.line_of_business",
        "claim.policy_number",
        "claim.source_system",
        "exposure.exposure_id",
        "exposure.claim_id",
        "exposure.exposure_type",
        "exposure.coverage_type",
        "exposure.claimant_id",
        "claimant.claimant_id",
        "claimant.claim_id",
        "claimant.role",
        "claimant.first_name",
        "claimant.last_name",
        "transaction.transaction_id",
        "transaction.claim_id",
        "transaction.transaction_type",
        "transaction.amount",
        "transaction.transaction_date",
    }
)

_TOP_LEVEL_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("claim", Claim),
    ("exposure", Exposure),
    ("claimant", Claimant),
    ("transaction", Transaction),
    ("policy", PolicySnapshot),
)


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


def _walk_model(model: type[BaseModel], prefix: str) -> dict[str, str]:
    """Recursively collect dotted field paths and type labels."""
    fields: dict[str, str] = {}
    for name, field_info in model.model_fields.items():
        path = f"{prefix}.{name}"
        annotation = field_info.annotation
        inner = _unwrap(annotation)
        origin = get_origin(inner)
        if origin is list or origin is dict:
            fields[path] = _type_label(annotation)
            continue
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            fields.update(_walk_model(inner, path))
        else:
            fields[path] = _type_label(annotation)
    return fields


def get_universal_schema_fields() -> dict[str, str]:
    """Return all universal schema field paths and their type labels."""
    result: dict[str, str] = {}
    for prefix, model in _TOP_LEVEL_MODELS:
        result.update(_walk_model(model, prefix))
    return result


def get_optional_schema_fields() -> set[str]:
    """Return schema paths that are not in the critical required set."""
    return set(get_universal_schema_fields()) - CRITICAL_REQUIRED_TARGETS


def schema_leaf(path: str) -> str:
    """Return the final segment of a dotted schema path."""
    return path.rsplit(".", 1)[-1]
