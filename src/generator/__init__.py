"""Adapter Code Generator — deterministic Jinja2 code generation."""

from src.generator.engine import GenerationResult, GeneratorEngine
from src.generator.registry import AdapterInfo, AdapterRegistry
from src.generator.schema_introspector import FieldSpec, SchemaIntrospector

__all__ = [
    "AdapterInfo",
    "AdapterRegistry",
    "FieldSpec",
    "GenerationResult",
    "GeneratorEngine",
    "SchemaIntrospector",
]
