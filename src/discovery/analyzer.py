"""LLM-powered insurance field annotation."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

from src.config import validate_gemini_config
from src.discovery.profile import FieldInfo
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 40

_INSURANCE_SYSTEM_PROMPT = """You are an insurance data integration expert.
You understand ACORD standards, Guidewire ClaimCenter, Duck Creek Claims,
and legacy insurance systems.
For each field, provide insurance_annotation (insurance meaning)
and an updated confidence score (0.0-1.0).
If a field name is ambiguous, explain the ambiguity in the annotation.
Common synonyms: excess=deductible, FNOL=first notice of loss, LOB=line of business,
DOL/DT_OF_LSS=date of loss, CAT=catastrophe, SIU=special investigations unit,
TPA=third party administrator, BI=bodily injury, PD=property damage,
UM/UIM=uninsured/underinsured motorist, PIP=personal injury protection,
subrogation=recovery rights.
Return JSON matching the required schema with one entry per input field."""


class FieldAnnotationItem(BaseModel):
    """Single field annotation from the LLM."""

    model_config = ConfigDict(strict=True)

    source_name: str
    insurance_annotation: str
    confidence: float = Field(ge=0.0, le=1.0)


class FieldAnnotationBatch(BaseModel):
    """Batch of field annotations from the LLM."""

    model_config = ConfigDict(strict=True)

    fields: list[FieldAnnotationItem]


class InsuranceFieldAnalyzer:
    """Adds insurance domain annotations to discovered fields via LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLM client dependency."""
        self._llm_client = llm_client

    async def annotate_fields(
        self,
        fields: list[FieldInfo],
        source_format: str,
        notes: list[str],
    ) -> list[FieldInfo]:
        """Annotate fields with insurance semantics; chunk if more than 40 fields."""
        validate_gemini_config()
        if not fields:
            return []
        if len(fields) <= _CHUNK_SIZE:
            return await self._annotate_chunk(fields, source_format, notes)
        annotated: list[FieldInfo] = []
        for start in range(0, len(fields), _CHUNK_SIZE):
            chunk = fields[start : start + _CHUNK_SIZE]
            annotated.extend(await self._annotate_chunk(chunk, source_format, notes))
        return annotated

    async def _annotate_chunk(
        self,
        fields: list[FieldInfo],
        source_format: str,
        notes: list[str],
    ) -> list[FieldInfo]:
        """Annotate a single chunk of fields."""
        payload = [
            {
                "source_name": f.source_name,
                "inferred_type": f.inferred_type,
                "sample_values": f.sample_values,
                "nesting_path": f.nesting_path,
            }
            for f in fields
        ]
        user_prompt = json.dumps(
            {
                "source_format": source_format,
                "notes": notes,
                "fields": payload,
            },
            indent=2,
        )
        batch = await self._llm_client.analyze(
            _INSURANCE_SYSTEM_PROMPT,
            user_prompt,
            FieldAnnotationBatch,
        )
        by_name = {item.source_name: item for item in batch.fields}
        result: list[FieldInfo] = []
        for field in fields:
            item = by_name.get(field.source_name)
            if item is None:
                logger.warning("LLM response missing field: %s", field.source_name)
                result.append(field)
                continue
            result.append(
                field.model_copy(
                    update={
                        "insurance_annotation": item.insurance_annotation,
                        "confidence": item.confidence,
                    }
                )
            )
        extra = set(by_name) - {f.source_name for f in fields}
        if extra:
            logger.warning("LLM response included unknown fields: %s", extra)
        return result
