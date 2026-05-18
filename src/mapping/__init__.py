"""Mapping Engine — map client fields to the universal schema."""

from src.mapping.config import (
    ConfidenceSummary,
    FieldMapping,
    FieldTransform,
    GapInfo,
    MappingConfig,
    MatchType,
    TransformType,
    collect_unique_transforms,
)
from src.mapping.engine import MappingEngine

__all__ = [
    "ConfidenceSummary",
    "FieldMapping",
    "FieldTransform",
    "GapInfo",
    "MappingConfig",
    "MappingEngine",
    "MatchType",
    "TransformType",
    "collect_unique_transforms",
]
