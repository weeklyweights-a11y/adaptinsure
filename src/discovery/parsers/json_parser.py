"""JSON and OpenAPI parsers for the Discovery Engine."""

from __future__ import annotations

import json
from typing import Any

import yaml

from src.discovery.parsers._utils import accumulator_to_fields, flatten_json_records
from src.discovery.parsers.types import ParserResult
from src.discovery.profile import FieldInfo, InferredType

_OPENAPI_TYPE_MAP: dict[str, InferredType] = {
    "string": "string",
    "integer": "integer",
    "number": "decimal",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def parse_json(raw_input: str) -> ParserResult:
    """Parse JSON data and extract field information."""
    data = json.loads(raw_input)
    records: list[dict[str, Any]]
    if isinstance(data, list):
        records = [r for r in data if isinstance(r, dict)]
        record_count = len(records)
    elif isinstance(data, dict):
        records = [data]
        record_count = 1
    else:
        records = []
        record_count = 0

    accumulator = flatten_json_records(records)
    fields = accumulator_to_fields(accumulator)
    raw_sample = records[0] if records else None
    return ParserResult(
        fields=fields,
        record_count=record_count,
        raw_sample=raw_sample,
        parser_notes=[],
    )


def parse_openapi_spec(spec_input: str) -> ParserResult:
    """Parse OpenAPI/Swagger spec and extract schema field information."""
    stripped = spec_input.strip()
    if stripped.startswith("{"):
        spec = json.loads(stripped)
    else:
        spec = yaml.safe_load(stripped)
    if not isinstance(spec, dict):
        return ParserResult(fields=[], record_count=0, raw_sample=None, parser_notes=[])

    schemas: dict[str, Any] = {}
    if "components" in spec and isinstance(spec["components"], dict):
        schemas = spec["components"].get("schemas") or {}
    elif "definitions" in spec:
        schemas = spec.get("definitions") or {}

    fields: list[FieldInfo] = []
    for schema_name, schema_def in schemas.items():
        if not isinstance(schema_def, dict):
            continue
        resolved = _resolve_schema(schema_def, schemas)
        _walk_openapi_schema(schema_name, resolved, schemas, fields, schema_name)

    return ParserResult(
        fields=fields,
        record_count=len(schemas),
        raw_sample=spec if len(str(spec)) < 2000 else None,
        parser_notes=["OpenAPI specification parsed"],
    )


def _resolve_schema(schema: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    """Resolve one-level $ref in a schema."""
    ref = schema.get("$ref")
    if not ref or not isinstance(ref, str):
        return schema
    ref_name = ref.rsplit("/", 1)[-1]
    target = schemas.get(ref_name)
    if isinstance(target, dict):
        merged = dict(target)
        merged.update({k: v for k, v in schema.items() if k != "$ref"})
        return merged
    return schema


def _walk_openapi_schema(
    schema_name: str,
    schema: dict[str, Any],
    schemas: dict[str, Any],
    fields: list[FieldInfo],
    path_prefix: str,
) -> None:
    """Walk OpenAPI schema properties and append FieldInfo entries."""
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return
    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            continue
        prop_def = _resolve_schema(prop_def, schemas)
        nesting = f"{path_prefix}.{prop_name}"
        oa_type = prop_def.get("type", "string")
        inferred = _OPENAPI_TYPE_MAP.get(str(oa_type), "string")
        fmt = prop_def.get("format")
        format_pattern = str(fmt) if fmt else None
        fields.append(
            FieldInfo(
                source_name=prop_name,
                inferred_type=inferred,
                description=prop_def.get("description"),
                format_pattern=format_pattern,
                nesting_path=nesting,
                confidence=0.5,
            )
        )
        if oa_type == "object" or "properties" in prop_def:
            _walk_openapi_schema(prop_name, prop_def, schemas, fields, nesting)


def is_openapi_document(data: dict[str, Any]) -> bool:
    """Return True if dict looks like an OpenAPI/Swagger document."""
    return "openapi" in data or "swagger" in data
