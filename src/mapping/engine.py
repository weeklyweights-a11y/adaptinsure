"""Mapping Engine orchestrator — ClientProfile to MappingConfig."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from src.discovery.profile import ClientProfile, FieldInfo
from src.exceptions import ConfigError, LLMError, MappingError
from src.llm.client import LLMClient
from src.mapping.codes import (
    MAP_INVALID_PROFILE,
    MAP_MATCH_FAILED,
)
from src.mapping.confidence import ConfidenceScorer
from src.mapping.config import GapType, MappingConfig, collect_unique_transforms
from src.mapping.direct_matcher import DirectMatcher
from src.mapping.gap_analyzer import GapAnalyzer
from src.mapping.knowledge_base import MappingKnowledgeBase
from src.mapping.schema_registry import SCHEMA_VERSION
from src.mapping.semantic_matcher import SemanticMatcher
from src.mapping.transform_detector import TransformDetector

logger = logging.getLogger(__name__)

_ALLOWED_FORMATS = frozenset({"json", "xml", "csv"})


def _source_key(field: FieldInfo) -> str:
    return field.nesting_path or field.source_name


class MappingEngine:
    """Orchestrate direct, KB, semantic matching and produce MappingConfig."""

    def __init__(
        self,
        llm_client: LLMClient,
        knowledge_base: MappingKnowledgeBase,
        *,
        semantic_matcher: SemanticMatcher | None = None,
    ) -> None:
        """Initialize engine with LLM client and knowledge base."""
        self._llm = llm_client
        self._kb = knowledge_base
        self._direct = DirectMatcher()
        self._semantic = semantic_matcher or SemanticMatcher(llm_client)
        self._transform = TransformDetector()
        self._gap = GapAnalyzer()
        self._scorer = ConfidenceScorer()

    def _validate_profile(self, profile: ClientProfile) -> None:
        if not profile.client_name.strip():
            raise MappingError(
                MAP_INVALID_PROFILE,
                "client_name is required",
            )
        if profile.source_format not in _ALLOWED_FORMATS:
            raise MappingError(
                MAP_INVALID_PROFILE,
                f"Unsupported source_format: {profile.source_format}",
                details={"source_format": profile.source_format},
            )

    async def map(self, profile: ClientProfile) -> MappingConfig:
        """Run the full mapping pipeline and return MappingConfig."""
        self._validate_profile(profile)
        notes: list[str] = []
        all_mappings: list = []
        all_gaps: list = []
        mapped_sources: set[str] = set()
        mapped_targets: set[str] = set()
        semantic_gap_fields: set[str] = set()

        try:
            start = time.perf_counter()
            known_examples = self._kb.get_known_mappings(profile.source_format)
            notes.append(f"Knowledge base primed with {len(known_examples)} examples")
            logger.info("KB priming: %s examples", len(known_examples))

            start = time.perf_counter()
            direct_mappings = self._direct.match(profile.fields)
            for m in direct_mappings:
                mapped_sources.add(m.source_field)
                mapped_targets.add(m.target_field)
            elapsed = (time.perf_counter() - start) * 1000
            msg = (
                f"Direct matcher: {len(direct_mappings)}/{len(profile.fields)} "
                f"fields matched in {elapsed:.1f}ms"
            )
            logger.info(msg)
            notes.append(msg)
            all_mappings.extend(direct_mappings)

            unmatched = [
                f
                for f in profile.fields
                if _source_key(f) not in mapped_sources
            ]

            start = time.perf_counter()
            kb_hits = 0
            still_unmatched: list[FieldInfo] = []
            for field in unmatched:
                hit = self._kb.lookup(field.source_name, profile.source_format)
                if hit is None or hit.target_field in mapped_targets:
                    still_unmatched.append(field)
                    continue
                adjusted = hit.model_copy(
                    update={
                        "confidence": round(hit.confidence * 0.9, 4),
                        "reasoning": f"{hit.reasoning} (knowledge base)",
                    }
                )
                all_mappings.append(adjusted)
                mapped_sources.add(field.source_name)
                mapped_targets.add(hit.target_field)
                kb_hits += 1
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Knowledge base: {kb_hits} hits in {elapsed:.1f}ms"
            logger.info(msg)
            notes.append(msg)

            start = time.perf_counter()
            semantic_outcome = await self._semantic.match(
                still_unmatched,
                list(mapped_targets),
                known_examples=known_examples or None,
            )
            for m in semantic_outcome.mappings:
                mapped_sources.add(m.source_field)
                mapped_targets.add(m.target_field)
                if m.transform and m.transform.parameters:
                    extras = m.transform.parameters.get("source_fields")
                    if isinstance(extras, list):
                        for name in extras:
                            if isinstance(name, str):
                                mapped_sources.add(name)
            for g in semantic_outcome.gaps:
                if g.gap_type == GapType.UNMAPPED_SOURCE:
                    semantic_gap_fields.add(g.field_name)
            all_mappings.extend(semantic_outcome.mappings)
            all_gaps.extend(semantic_outcome.gaps)
            elapsed = (time.perf_counter() - start) * 1000
            msg = (
                f"Semantic matcher: {len(semantic_outcome.mappings)} mappings, "
                f"{len(semantic_outcome.gaps)} gaps in {elapsed:.1f}ms"
            )
            logger.info(msg)
            notes.append(msg)

            start = time.perf_counter()
            transform_result = self._transform.detect_transforms(
                all_mappings,
                profile.fields,
            )
            all_mappings = transform_result.mappings
            all_gaps.extend(transform_result.gaps)
            for m in all_mappings:
                mapped_sources.add(m.source_field)
                mapped_targets.add(m.target_field)
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Transform detector: {len(all_mappings)} mappings in {elapsed:.1f}ms"
            logger.info(msg)
            notes.append(msg)

            start = time.perf_counter()
            analyzer_gaps = self._gap.analyze(
                all_mappings,
                profile.fields,
                mapped_sources,
                semantic_gap_fields=semantic_gap_fields,
            )
            all_gaps.extend(analyzer_gaps)
            all_gaps = _dedupe_gaps(all_gaps)
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Gap analyzer: {len(all_gaps)} gaps in {elapsed:.1f}ms"
            logger.info(msg)
            notes.append(msg)

            summary = self._scorer.compute_summary(
                all_mappings,
                all_gaps,
                profile.total_fields_detected,
            )

            config = MappingConfig(
                client_name=profile.client_name,
                source_format=profile.source_format,
                schema_version=SCHEMA_VERSION,
                field_mappings=all_mappings,
                transforms=collect_unique_transforms(all_mappings),
                gaps=all_gaps,
                confidence_summary=summary,
                created_at=datetime.now(UTC),
                notes=notes,
            )
            return config

        except (ConfigError, LLMError):
            raise
        except MappingError:
            raise
        except Exception as exc:
            raise MappingError(
                MAP_MATCH_FAILED,
                f"Mapping pipeline failed: {exc}",
                details={"step": "orchestration"},
            ) from exc


def _dedupe_gaps(gaps: list) -> list:
    """Deduplicate gaps by field_name and gap_type."""
    from src.mapping.gap_analyzer import _dedupe_gaps as dedupe

    return dedupe(gaps)
