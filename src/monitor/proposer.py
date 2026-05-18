"""LLM-powered fix proposer for schema drift."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.config import get_settings
from src.llm.client import LLMClient
from src.mapping.config import MappingConfig
from src.monitor.differ import SchemaDiff
from src.monitor.expected_schema import ExpectedSchema


class FixType(StrEnum):
    """Kind of mapping config fix."""

    UPDATE_FIELD_NAME = "update_field_name"
    UPDATE_TRANSFORM = "update_transform"
    ADD_MAPPING = "add_mapping"
    REMOVE_MAPPING = "remove_mapping"
    UPDATE_ENUM_MAP = "update_enum_map"
    MANUAL_REVIEW = "manual_review"


_AUTO_APPLICABLE = frozenset(
    {
        FixType.UPDATE_FIELD_NAME,
        FixType.UPDATE_TRANSFORM,
        FixType.UPDATE_ENUM_MAP,
    }
)


class ConfigChange(BaseModel):
    """Single change to apply to MappingConfig."""

    model_config = ConfigDict(strict=True)

    change_type: Annotated[str, Field(description="Config change kind")]
    field_path: Annotated[str, Field(description="Field or mapping path")]
    old_value: Annotated[str | None, Field(default=None)]
    new_value: Annotated[str | None, Field(default=None)]
    explanation: Annotated[str, Field(min_length=1)]


class ProposedFix(BaseModel):
    """Proposed fix for a schema drift."""

    model_config = ConfigDict(strict=True)

    diff: Annotated[SchemaDiff, Field(description="Triggering drift")]
    fix_type: Annotated[FixType, Field(description="Fix category")]
    description: Annotated[str, Field(min_length=1)]
    config_changes: Annotated[list[ConfigChange], Field(default_factory=list)]
    auto_applicable: Annotated[bool, Field(default=False)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(min_length=1)]


class ProposedFixResponse(BaseModel):
    """Structured LLM response for fix proposal."""

    model_config = ConfigDict(strict=True)

    fix_type: FixType
    description: str
    config_changes: list[ConfigChange]
    auto_applicable: bool
    confidence: float
    reasoning: str


class FixProposer:
    """Propose mapping config updates for detected drift."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize with optional LLM client override for tests."""
        settings = get_settings()
        self._llm = llm_client or LLMClient(model=settings.gemini_model_mapping)

    async def propose_fix(
        self,
        diff: SchemaDiff,
        current_config: MappingConfig,
        expected_schema: ExpectedSchema,
    ) -> ProposedFix:
        """Analyze drift and return a proposed config fix."""
        mapping = _find_mapping(current_config, diff.field_name)
        target = diff.target_field or (mapping.target_field if mapping else "unknown")
        transform_desc = "none"
        if mapping and mapping.transform:
            transform_desc = mapping.transform.transform_type.value

        system_prompt = (
            "You are an insurance data integration expert. "
            "Return JSON matching the required schema."
        )
        user_prompt = (
            f"Client: {expected_schema.client_name}\n"
            f"Drift: {diff.description}\n"
            f"Type: {diff.diff_type.value}\n"
            f"Source field: {diff.field_name}\n"
            f"Target field: {target}\n"
            f"Transform: {transform_desc}\n"
            f"Suggested rename: {diff.suggested_rename}\n"
            "Propose a fix to the mapping config."
        )

        response = await self._llm.analyze(
            system_prompt,
            user_prompt,
            ProposedFixResponse,
            temperature=0.0,
        )
        fix_type = response.fix_type
        auto = response.auto_applicable and fix_type in _AUTO_APPLICABLE
        if fix_type in _AUTO_APPLICABLE and not response.auto_applicable:
            auto = True
        if fix_type not in _AUTO_APPLICABLE:
            auto = False
        return ProposedFix(
            diff=diff,
            fix_type=fix_type,
            description=response.description,
            config_changes=response.config_changes,
            auto_applicable=auto,
            confidence=response.confidence,
            reasoning=response.reasoning,
        )


def _find_mapping(config: MappingConfig, source_field: str) -> object | None:
    """Find field mapping by source field name."""
    for mapping in config.field_mappings:
        if mapping.source_field == source_field:
            return mapping
    return None
