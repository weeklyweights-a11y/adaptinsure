"""LLM-powered semantic field matcher for the Mapping Engine."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.config import validate_gemini_config
from src.discovery.profile import FieldInfo
from src.exceptions import LLMError
from src.llm.client import LLMClient
from src.mapping.config import FieldMapping, GapInfo, GapType, MatchType
from src.mapping.schema_registry import get_universal_schema_fields

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10

_INSURANCE_SYNONYMS = """
Insurance domain synonyms (non-exhaustive):
- excess = deductible
- FNOL = first notice of loss = reported_date
- LOB = line of business
- DOL = date of loss = loss_date
- CAT = catastrophe
- BI = bodily injury
- PD = property damage (context: exposure) OR paid amount when clearly financial
- UM/UIM = uninsured/underinsured motorist
- PIP = personal injury protection
- SIR = self-insured retention (similar to deductible)
- TPA = third party administrator
- SIU = special investigations unit (fraud-related)
- subrogation = recovery rights
- indemnity = payment for loss
- salvage = recovered property value
- adjuster = claims handler
- peril = cause of loss
"""


class SemanticMatchResult(BaseModel):
    """Single field semantic match from the LLM."""

    model_config = ConfigDict(strict=True)

    source_name: Annotated[str, Field(description="Source field name")]
    target_field: Annotated[str | None, Field(description="Universal schema path or null")]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(min_length=1)]
    needs_transform: Annotated[bool, Field(default=False)]
    transform_type: Annotated[str | None, Field(default=None)]
    source_format: Annotated[str | None, Field(default=None)]


class SemanticMatchBatch(BaseModel):
    """Batch of semantic match results."""

    model_config = ConfigDict(strict=True)

    results: Annotated[list[SemanticMatchResult], Field(default_factory=list)]


@dataclass(frozen=True)
class SemanticMatchOutcome:
    """Mappings and gaps produced by semantic matching."""

    mappings: list[FieldMapping]
    gaps: list[GapInfo]


class SemanticMatcher:
    """Match unmatched fields using Gemini with insurance domain context."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLM client (model set per call)."""
        self._llm = llm_client
        self._schema_fields = get_universal_schema_fields()

    def _system_prompt(
        self,
        candidates: list[str],
        known_examples: list[FieldMapping] | None,
    ) -> str:
        """Build the system prompt for semantic matching."""
        examples_block = ""
        if known_examples:
            payload = [
                {
                    "source_field": m.source_field,
                    "target_field": m.target_field,
                    "confidence": m.confidence,
                    "reasoning": m.reasoning,
                }
                for m in known_examples[:20]
            ]
            examples_block = f"\nKnown good mappings:\n{json.dumps(payload, indent=2)}\n"
        candidate_list = "\n".join(f"- {path}" for path in sorted(candidates))
        return (
            "You are an insurance data integration expert. Map insurer source fields "
            "to the universal claims schema. Return JSON matching the output schema.\n"
            f"{_INSURANCE_SYNONYMS}\n"
            f"{examples_block}\n"
            "Available target fields (choose only from this list or null):\n"
            f"{candidate_list}\n"
        )

    def _user_prompt(self, fields: list[FieldInfo]) -> str:
        """Build the user prompt for a batch of fields."""
        items = []
        for field in fields:
            items.append(
                {
                    "source_name": field.source_name,
                    "inferred_type": field.inferred_type,
                    "sample_values": field.sample_values,
                    "description": field.description,
                    "insurance_annotation": field.insurance_annotation,
                    "nesting_path": field.nesting_path,
                }
            )
        return f"Map these source fields:\n{json.dumps(items, indent=2)}"

    async def match(
        self,
        unmatched_fields: list[FieldInfo],
        already_mapped_targets: list[str],
        *,
        known_examples: list[FieldMapping] | None = None,
    ) -> SemanticMatchOutcome:
        """Match unmatched fields via Gemini in batches of up to 10."""
        validate_gemini_config()
        mapped_set = set(already_mapped_targets)
        candidates = [p for p in self._schema_fields if p not in mapped_set]
        mappings: list[FieldMapping] = []
        gaps: list[GapInfo] = []
        system_prompt = self._system_prompt(candidates, known_examples)

        for start in range(0, len(unmatched_fields), _BATCH_SIZE):
            batch = unmatched_fields[start : start + _BATCH_SIZE]
            user_prompt = self._user_prompt(batch)
            try:
                result = await self._llm.analyze(
                    system_prompt,
                    user_prompt,
                    SemanticMatchBatch,
                )
            except LLMError:
                raise
            except Exception as exc:
                msg = f"Semantic matching failed: {exc}"
                raise LLMError("LLM_SEMANTIC_FAILED", msg) from exc

            by_source = {r.source_name: r for r in result.results}
            for field in batch:
                item = by_source.get(field.source_name)
                if item is None:
                    gaps.append(
                        GapInfo(
                            field_name=field.source_name,
                            gap_type=GapType.UNMAPPED_SOURCE,
                            severity="warning",
                            description=f"No semantic result for {field.source_name}",
                            suggestion=(
                                "This source field has no equivalent in the universal schema. "
                                "It will be preserved in raw_data."
                            ),
                        )
                    )
                    continue
                if item.target_field is None:
                    gaps.append(
                        GapInfo(
                            field_name=field.source_name,
                            gap_type=GapType.UNMAPPED_SOURCE,
                            severity="warning",
                            description=item.reasoning,
                            suggestion=(
                                "This source field has no equivalent in the universal schema. "
                                "It will be preserved in raw_data."
                            ),
                        )
                    )
                    continue
                if item.target_field not in self._schema_fields:
                    gaps.append(
                        GapInfo(
                            field_name=field.source_name,
                            gap_type=GapType.AMBIGUOUS,
                            severity="warning",
                            description=f"Invalid target {item.target_field!r}",
                            suggestion="Please review and confirm or correct this mapping.",
                        )
                    )
                    continue
                if item.target_field in mapped_set:
                    gaps.append(
                        GapInfo(
                            field_name=field.source_name,
                            gap_type=GapType.AMBIGUOUS,
                            severity="warning",
                            description=f"Target {item.target_field} already mapped",
                            suggestion="Please review and confirm or correct this mapping.",
                        )
                    )
                    continue

                match_type = (
                    MatchType.MANUAL if item.confidence < 0.5 else MatchType.SEMANTIC
                )
                reasoning = item.reasoning
                if item.needs_transform:
                    reasoning = f"{reasoning} (transform deferred to TransformDetector)"
                mappings.append(
                    FieldMapping(
                        source_field=field.source_name,
                        source_path=field.nesting_path,
                        target_field=item.target_field,
                        match_type=match_type,
                        confidence=item.confidence,
                        reasoning=reasoning,
                        transform=None,
                    )
                )
                mapped_set.add(item.target_field)

        return SemanticMatchOutcome(mappings=mappings, gaps=gaps)
