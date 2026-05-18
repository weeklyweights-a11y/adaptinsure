"""Tests for the Mapping Engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.mapping.config import (
    ConfidenceSummary,
    FieldMapping,
    FieldTransform,
    GapInfo,
    GapType,
    MappingConfig,
    MatchType,
    TransformType,
    collect_unique_transforms,
)

UTC = timezone.utc


class TestMappingModels:
    """MappingConfig model tests (spec Step 1)."""

    def test_field_mapping_creates(self) -> None:
        """FieldMapping with required fields creates successfully."""
        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.95,
            reasoning="Exact name match",
        )
        assert mapping.source_field == "lossDate"

    def test_field_mapping_confidence_bounds(self) -> None:
        """FieldMapping confidence constrained to 0.0-1.0."""
        with pytest.raises(ValidationError):
            FieldMapping(
                source_field="x",
                target_field="claim.x",
                match_type=MatchType.DIRECT,
                confidence=1.5,
                reasoning="bad",
            )

    def test_field_mapping_with_transform(self) -> None:
        """FieldMapping with transform creates successfully."""
        transform = FieldTransform(
            transform_type=TransformType.DATE_FORMAT,
            source_format="MM/DD/YYYY",
            target_format="ISO 8601",
        )
        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="Date field",
            transform=transform,
        )
        assert mapping.transform is not None

    def test_field_mapping_without_transform(self) -> None:
        """FieldMapping without transform allows None."""
        mapping = FieldMapping(
            source_field="claimId",
            target_field="claim.claim_id",
            match_type=MatchType.DIRECT,
            confidence=0.95,
            reasoning="Exact match",
            transform=None,
        )
        assert mapping.transform is None

    def test_mapping_config_creates(self) -> None:
        """MappingConfig with mappings, transforms, and gaps creates."""
        summary = ConfidenceSummary(
            total_fields=2,
            mapped_fields=1,
            unmapped_fields=1,
            high_confidence_count=1,
            medium_confidence_count=0,
            low_confidence_count=0,
            average_confidence=0.9,
        )
        config = MappingConfig(
            client_name="test",
            source_format="json",
            schema_version="1.0.0",
            field_mappings=[
                FieldMapping(
                    source_field="a",
                    target_field="claim.a",
                    match_type=MatchType.DIRECT,
                    confidence=0.9,
                    reasoning="match",
                )
            ],
            transforms=[],
            gaps=[
                GapInfo(
                    field_name="b",
                    gap_type=GapType.UNMAPPED_SOURCE,
                    severity="warning",
                    description="unmapped",
                )
            ],
            confidence_summary=summary,
            created_at=datetime.now(UTC),
        )
        assert len(config.field_mappings) == 1

    def test_mapping_config_empty_lists(self) -> None:
        """MappingConfig with empty lists creates successfully."""
        summary = ConfidenceSummary(
            total_fields=0,
            mapped_fields=0,
            unmapped_fields=0,
            high_confidence_count=0,
            medium_confidence_count=0,
            low_confidence_count=0,
            average_confidence=0.0,
        )
        config = MappingConfig(
            client_name="empty",
            source_format="csv",
            schema_version="1.0.0",
            field_mappings=[],
            transforms=[],
            gaps=[],
            confidence_summary=summary,
            created_at=datetime.now(UTC),
        )
        assert config.field_mappings == []

    def test_confidence_summary_requires_review_low_confidence(self) -> None:
        """requires_review True when low confidence count > 0."""
        summary = ConfidenceSummary(
            total_fields=5,
            mapped_fields=5,
            unmapped_fields=0,
            high_confidence_count=3,
            medium_confidence_count=1,
            low_confidence_count=1,
            average_confidence=0.7,
        )
        assert summary.requires_review is True

    def test_confidence_summary_requires_review_critical_gap_flag(self) -> None:
        """requires_review True when explicitly set for critical gaps."""
        summary = ConfidenceSummary(
            total_fields=5,
            mapped_fields=5,
            unmapped_fields=0,
            high_confidence_count=5,
            medium_confidence_count=0,
            low_confidence_count=0,
            average_confidence=0.95,
            requires_review=True,
        )
        assert summary.requires_review is True

    def test_confidence_summary_no_review_when_all_high(self) -> None:
        """requires_review False when all high confidence and no flags."""
        summary = ConfidenceSummary(
            total_fields=3,
            mapped_fields=3,
            unmapped_fields=0,
            high_confidence_count=3,
            medium_confidence_count=0,
            low_confidence_count=0,
            average_confidence=0.95,
        )
        assert summary.requires_review is False

    def test_gap_info_critical(self) -> None:
        """GapInfo with critical severity creates."""
        gap = GapInfo(
            field_name="claim.loss_date",
            gap_type=GapType.MISSING_REQUIRED,
            severity="critical",
            description="Required field missing",
        )
        assert gap.severity == "critical"

    def test_field_transform_parameters(self) -> None:
        """FieldTransform with parameters dict creates."""
        transform = FieldTransform(
            transform_type=TransformType.BOOLEAN_PARSE,
            parameters={"true_values": ["Y"], "false_values": ["N"]},
        )
        assert transform.parameters is not None

    def test_enums_have_expected_values(self) -> None:
        """MatchType, TransformType, GapType have expected members."""
        assert MatchType.DIRECT == "direct"
        assert TransformType.ENUM_MAP == "enum_map"
        assert GapType.MISSING_REQUIRED == "missing_required"


class TestCollectUniqueTransforms:
    """collect_unique_transforms helper tests."""

    def test_dedupes_identical_transforms(self) -> None:
        """Identical transforms on multiple mappings appear once."""
        transform = FieldTransform(
            transform_type=TransformType.DATE_FORMAT,
            source_format="YYYY-MM-DD",
            target_format="ISO 8601",
        )
        mappings = [
            FieldMapping(
                source_field="a",
                target_field="claim.a",
                match_type=MatchType.DIRECT,
                confidence=0.9,
                reasoning="a",
                transform=transform,
            ),
            FieldMapping(
                source_field="b",
                target_field="claim.b",
                match_type=MatchType.DIRECT,
                confidence=0.9,
                reasoning="b",
                transform=transform,
            ),
        ]
        assert len(collect_unique_transforms(mappings)) == 1

    def test_skips_none_transforms(self) -> None:
        """Mappings without transforms contribute nothing."""
        mappings = [
            FieldMapping(
                source_field="a",
                target_field="claim.a",
                match_type=MatchType.DIRECT,
                confidence=0.9,
                reasoning="a",
            ),
        ]
        assert collect_unique_transforms(mappings) == []


def _field(name: str, **kwargs: object) -> "FieldInfo":
    from src.discovery.profile import FieldInfo

    inferred = kwargs.pop("inferred_type", "string")
    return FieldInfo(source_name=name, inferred_type=inferred, **kwargs)  # type: ignore[arg-type]


class TestSchemaRegistry:
    """Schema registry introspection tests."""

    def test_get_universal_schema_fields_includes_claim_paths(self) -> None:
        from src.mapping.schema_registry import get_universal_schema_fields

        fields = get_universal_schema_fields()
        assert "claim.loss_date" in fields
        assert fields["claim.loss_date"] == "datetime"
        assert "exposure.reserved_amount" in fields
        assert "claimant.first_name" in fields
        assert "transaction.amount" in fields

    def test_critical_required_targets_subset_of_schema(self) -> None:
        from src.mapping.schema_registry import (
            CRITICAL_REQUIRED_TARGETS,
            get_universal_schema_fields,
        )

        schema = get_universal_schema_fields()
        for target in CRITICAL_REQUIRED_TARGETS:
            if target == "claim.loss_location":
                assert any(p.startswith("claim.loss_location") for p in schema)
            else:
                assert target in schema


class TestDirectMatcher:
    """DirectMatcher rule tests."""

    def test_exact_match_claim_id(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("claim_id")])
        assert len(mappings) == 1
        assert mappings[0].target_field == "claim.claim_id"
        assert mappings[0].confidence == 0.95

    def test_case_insensitive_claim_id(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("ClaimId")])
        assert mappings[0].target_field == "claim.claim_id"
        assert mappings[0].confidence == 0.90

    def test_camelcase_loss_date(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("lossDate")])
        assert mappings[0].target_field == "claim.loss_date"
        assert mappings[0].confidence == 0.85

    def test_prefix_strip_clm_nbr(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("clm_nbr")])
        assert mappings[0].target_field == "claim.claim_number"
        assert mappings[0].confidence == 0.75

    def test_abbreviation_loss_dt(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("loss_dt")])
        assert mappings[0].target_field == "claim.loss_date"
        assert mappings[0].confidence == 0.70

    def test_abbreviation_rsv_amt(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        mappings = DirectMatcher().match([_field("rsv_amt")])
        assert mappings[0].target_field == "exposure.reserved_amount"

    def test_no_match_xyz_foo_bar(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        assert DirectMatcher().match([_field("xyz_foo_bar")]) == []

    def test_status_ambiguous_no_match(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        assert DirectMatcher().match([_field("status")]) == []

    def test_multiple_fields_matched(self) -> None:
        from src.mapping.direct_matcher import DirectMatcher

        fields = [
            _field("claim_id"),
            _field("lossDate"),
            _field("policy_number"),
            _field("exposure_id"),
            _field("claimant_id"),
        ]
        mappings = DirectMatcher().match(fields)
        assert len(mappings) == 5
        assert all(m.match_type == MatchType.DIRECT for m in mappings)


class TestTransformDetector:
    """TransformDetector tests."""

    def test_iso_date_transform(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("lossDate", inferred_type="string", sample_values=["2024-01-15"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.transform_type == TransformType.DATE_FORMAT
        assert result.mappings[0].transform.source_format == "YYYY-MM-DD"

    def test_us_date_transform(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("lossDate", inferred_type="string", sample_values=["01/15/2024"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.source_format == "MM/DD/YYYY"

    def test_packed_date_transform(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="DT_OF_LSS",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("DT_OF_LSS", inferred_type="string", sample_values=["20240115"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.source_format == "YYYYMMDD"

    def test_currency_parse(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="amt",
            target_field="exposure.paid_amount",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("amt", inferred_type="string", sample_values=["$1,234.56"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.transform_type == TransformType.CURRENCY_PARSE

    def test_plain_decimal_type_cast_not_currency(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="amt",
            target_field="exposure.paid_amount",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("amt", inferred_type="string", sample_values=["1234.56"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.transform_type == TransformType.TYPE_CAST

    def test_boolean_yn(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="flag",
            target_field="claim.litigation_flag",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="match",
        )
        info = _field("flag", inferred_type="string", sample_values=["Y", "N"])
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is not None
        assert result.mappings[0].transform.transform_type == TransformType.BOOLEAN_PARSE

    def test_no_transform_when_types_align(self) -> None:
        from src.mapping.transform_detector import TransformDetector

        mapping = FieldMapping(
            source_field="claim_id",
            target_field="claim.claim_id",
            match_type=MatchType.DIRECT,
            confidence=0.95,
            reasoning="match",
        )
        info = _field("claim_id", inferred_type="string")
        result = TransformDetector().detect_transforms([mapping], [info])
        assert result.mappings[0].transform is None


class TestGapAnalyzer:
    """GapAnalyzer tests."""

    def test_no_critical_gaps_when_required_mapped(self) -> None:
        from src.mapping.gap_analyzer import GapAnalyzer
        from src.mapping.schema_registry import CRITICAL_REQUIRED_TARGETS

        mappings = [
            FieldMapping(
                source_field=f"f{i}",
                target_field=t,
                match_type=MatchType.DIRECT,
                confidence=0.95,
                reasoning="test",
            )
            for i, t in enumerate(CRITICAL_REQUIRED_TARGETS)
        ]
        gaps = GapAnalyzer().analyze(mappings, [], set(m.source_field for m in mappings))
        critical = [g for g in gaps if g.severity == "critical"]
        assert critical == []

    def test_missing_loss_date_critical(self) -> None:
        from src.mapping.gap_analyzer import GapAnalyzer

        gaps = GapAnalyzer().analyze([], [], set())
        critical = [g for g in gaps if g.field_name == "claim.loss_date"]
        assert len(critical) == 1
        assert critical[0].severity == "critical"

    def test_unmapped_source_gap(self) -> None:
        from src.mapping.gap_analyzer import GapAnalyzer

        gaps = GapAnalyzer().analyze(
            [],
            [_field("custom_internal_ref")],
            set(),
        )
        unmapped = [g for g in gaps if g.gap_type == GapType.UNMAPPED_SOURCE]
        assert len(unmapped) == 1
        assert unmapped[0].suggestion is not None

    def test_low_confidence_gap(self) -> None:
        from src.mapping.gap_analyzer import GapAnalyzer

        mappings = [
            FieldMapping(
                source_field="x",
                target_field="claim.claim_id",
                match_type=MatchType.MANUAL,
                confidence=0.3,
                reasoning="uncertain",
            )
        ]
        gaps = GapAnalyzer().analyze(mappings, [_field("x")], {"x"})
        low = [g for g in gaps if g.gap_type == GapType.AMBIGUOUS and g.field_name == "x"]
        assert len(low) >= 1


class TestConfidenceScorer:
    """ConfidenceScorer tests."""

    def test_all_high_confidence(self) -> None:
        from src.mapping.confidence import ConfidenceScorer

        mappings = [
            FieldMapping(
                source_field="a",
                target_field="claim.claim_id",
                match_type=MatchType.DIRECT,
                confidence=0.95,
                reasoning="r",
            )
        ]
        summary = ConfidenceScorer().compute_summary(mappings, [], 1)
        assert summary.high_confidence_count == 1
        assert summary.requires_review is False

    def test_zero_mappings_requires_review(self) -> None:
        from src.mapping.confidence import ConfidenceScorer
        from src.mapping.gap_analyzer import GapAnalyzer

        gaps = GapAnalyzer().analyze([], [], set())
        summary = ConfidenceScorer().compute_summary([], gaps, 0)
        assert summary.average_confidence == 0.0
        assert summary.requires_review is True

    def test_critical_gap_requires_review(self) -> None:
        from src.mapping.confidence import ConfidenceScorer

        mappings = [
            FieldMapping(
                source_field="a",
                target_field="claim.claim_id",
                match_type=MatchType.DIRECT,
                confidence=0.95,
                reasoning="r",
            )
        ]
        gaps = [
            GapInfo(
                field_name="claim.loss_date",
                gap_type=GapType.MISSING_REQUIRED,
                severity="critical",
                description="missing",
            )
        ]
        summary = ConfidenceScorer().compute_summary(mappings, gaps, 1)
        assert summary.requires_review is True

    def test_unmapped_fields_count(self) -> None:
        from src.mapping.confidence import ConfidenceScorer

        mappings = [
            FieldMapping(
                source_field="a",
                target_field="claim.claim_id",
                match_type=MatchType.DIRECT,
                confidence=0.9,
                reasoning="r",
            )
        ]
        summary = ConfidenceScorer().compute_summary(mappings, [], 3)
        assert summary.unmapped_fields == 2


class TestMappingKnowledgeBase:
    """MappingKnowledgeBase tests."""

    def test_store_and_lookup(self, tmp_path: "Path") -> None:
        from pathlib import Path

        from src.mapping.knowledge_base import MappingKnowledgeBase

        kb = MappingKnowledgeBase(tmp_path)
        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.95,
            reasoning="known",
        )
        kb.store("client_a", "json", [mapping])
        assert (tmp_path / "client_a_json.json").exists()
        hit = kb.lookup("lossDate", "json")
        assert hit is not None
        assert hit.target_field == "claim.loss_date"

    def test_filters_low_confidence_on_store(self, tmp_path: "Path") -> None:
        from src.mapping.knowledge_base import MappingKnowledgeBase

        kb = MappingKnowledgeBase(tmp_path)
        low = FieldMapping(
            source_field="x",
            target_field="claim.claim_id",
            match_type=MatchType.DIRECT,
            confidence=0.5,
            reasoning="low",
        )
        kb.store("c", "json", [low])
        data = (tmp_path / "c_json.json").read_text(encoding="utf-8")
        assert "x" not in data or '"mappings": []' in data.replace(" ", "")

    def test_cross_client_lookup(self, tmp_path: "Path") -> None:
        from src.mapping.knowledge_base import MappingKnowledgeBase

        kb = MappingKnowledgeBase(tmp_path)
        mapping = FieldMapping(
            source_field="lossDate",
            target_field="claim.loss_date",
            match_type=MatchType.DIRECT,
            confidence=0.9,
            reasoning="other client",
        )
        kb.store("other_client", "json", [mapping])
        hit = kb.lookup("lossDate", "json")
        assert hit is not None

    def test_list_clients(self, tmp_path: "Path") -> None:
        from src.mapping.knowledge_base import MappingKnowledgeBase

        kb = MappingKnowledgeBase(tmp_path)
        kb.store("alpha", "csv", [])
        kb.store("beta", "xml", [])
        assert set(kb.list_clients()) == {"alpha", "beta"}


class TestMappingEngine:
    """MappingEngine integration tests."""

    @pytest.mark.asyncio
    async def test_guidewire_high_confidence(
        self,
        guidewire_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.discovery.profile import ClientProfile
        from src.llm.client import LLMClient
        from src.mapping.engine import MappingEngine

        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        config = await engine.map(guidewire_profile)  # type: ignore[arg-type]
        assert isinstance(config.confidence_summary.average_confidence, float)
        assert config.confidence_summary.average_confidence >= 0.8
        assert config.client_name == "guidewire_carrier"

    @pytest.mark.asyncio
    async def test_legacy_mixed_confidence(
        self,
        legacy_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.llm.client import LLMClient
        from src.mapping.engine import MappingEngine

        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        config = await engine.map(legacy_profile)  # type: ignore[arg-type]
        assert len(config.field_mappings) >= 2
        confidences = {m.confidence for m in config.field_mappings}
        assert max(confidences) >= 0.7
        assert min(confidences) <= 0.85

    @pytest.mark.asyncio
    async def test_acord_valid_config(
        self,
        acord_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.llm.client import LLMClient
        from src.mapping.config import MappingConfig
        from src.mapping.engine import MappingEngine

        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        config = await engine.map(acord_profile)  # type: ignore[arg-type]
        assert isinstance(config, MappingConfig)
        assert config.source_format == "xml"

    @pytest.mark.asyncio
    async def test_kb_priming_reduced_confidence(
        self,
        guidewire_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.llm.client import LLMClient
        from src.mapping.config import FieldMapping, MatchType
        from src.mapping.engine import MappingEngine
        from src.mapping.knowledge_base import MappingKnowledgeBase

        kb: MappingKnowledgeBase = tmp_knowledge_base  # type: ignore[assignment]
        kb.store(
            "other",
            "json",
            [
                FieldMapping(
                    source_field="assignedGroup",
                    target_field="claim.adjuster_name",
                    match_type=MatchType.SEMANTIC,
                    confidence=0.9,
                    reasoning="stored",
                )
            ],
        )
        profile = guidewire_profile  # type: ignore[assignment]
        fields = [f for f in profile.fields if f.source_name != "assignedGroup"]
        from src.discovery.profile import ClientProfile

        trimmed = profile.model_copy(
            update={
                "fields": fields,
                "total_fields_detected": len(fields),
            }
        )
        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            kb,
            semantic_matcher=mock_semantic_matcher,
        )
        config = await engine.map(trimmed)
        hit = next(
            (m for m in config.field_mappings if m.source_field == "assignedGroup"),
            None,
        )
        assert hit is None

        full = profile.model_copy(
            update={"fields": profile.fields, "total_fields_detected": len(profile.fields)}
        )
        config2 = await engine.map(full)
        hit2 = next(
            (m for m in config2.field_mappings if m.source_field == "assignedGroup"),
            None,
        )
        assert hit2 is not None
        assert hit2.confidence == pytest.approx(0.81, abs=0.01)
        assert "(knowledge base)" in hit2.reasoning

    @pytest.mark.asyncio
    async def test_invalid_source_format_raises(
        self,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.discovery.profile import ClientProfile, FieldInfo
        from src.exceptions import MappingError
        from src.llm.client import LLMClient
        from src.mapping.engine import MappingEngine

        profile = ClientProfile(
            client_name="x",
            source_format="unknown",
            detected_encoding="utf-8",
            total_records_sampled=0,
            total_fields_detected=0,
            fields=[],
            created_at=datetime.now(UTC),
        )
        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        with pytest.raises(MappingError):
            await engine.map(profile)

    @pytest.mark.asyncio
    async def test_total_fields_matches_profile(
        self,
        guidewire_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.llm.client import LLMClient
        from src.mapping.engine import MappingEngine

        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        profile = guidewire_profile  # type: ignore[assignment]
        config = await engine.map(profile)
        assert (
            config.confidence_summary.total_fields == profile.total_fields_detected
        )

    @pytest.mark.asyncio
    async def test_model_dump_json_round_trip(
        self,
        guidewire_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
    ) -> None:
        from src.llm.client import LLMClient
        from src.mapping.config import MappingConfig
        from src.mapping.engine import MappingEngine

        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        config = await engine.map(guidewire_profile)  # type: ignore[arg-type]
        restored = MappingConfig.model_validate_json(config.model_dump_json())
        assert restored.client_name == config.client_name

    @pytest.mark.asyncio
    async def test_pipeline_logs_steps(
        self,
        guidewire_profile: object,
        tmp_knowledge_base: object,
        mock_semantic_matcher: object,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging

        from src.llm.client import LLMClient
        from src.mapping.engine import MappingEngine

        caplog.set_level(logging.INFO)
        engine = MappingEngine(
            LLMClient(api_key="test-key"),
            tmp_knowledge_base,
            semantic_matcher=mock_semantic_matcher,
        )
        await engine.map(guidewire_profile)  # type: ignore[arg-type]
        assert any("Direct matcher:" in r.message for r in caplog.records)
