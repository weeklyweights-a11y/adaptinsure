"""End-to-end pipeline: discover -> map -> generate -> run adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.discovery.engine import DiscoveryEngine
from src.discovery.profile import FieldInfo
from src.generator.engine import GeneratorEngine
from src.generator.registry import AdapterRegistry
from src.llm.client import LLMClient
from src.mapping.config import FieldMapping, FieldTransform, MatchType, TransformType
from src.mapping.engine import MappingEngine
from src.mapping.semantic_matcher import SemanticMatchOutcome, SemanticMatcher
from src.schema.enums import ClaimStatus, LineOfBusiness, LossCause

UTC = timezone.utc

SAMPLE_JSON = json.dumps(
    [
        {
            "claimId": "GW-001",
            "claimNumber": "CLM-001",
            "lossDate": "2024-03-15",
            "claimState": "open",
            "reportedDate": "2024-03-16",
            "lossDescription": "Rear-end collision",
            "lossCause": "collision",
            "policyNumber": "POL-100",
            "totalIncurred": "5000.00",
            "totalPaid": "1200.50",
            "deductible": "500.00",
        },
        {
            "claimId": "GW-002",
            "claimNumber": "CLM-002",
            "lossDate": "2024-04-01",
            "claimState": "open",
            "reportedDate": "2024-04-02",
            "lossDescription": "Water damage",
            "lossCause": "water_damage",
            "policyNumber": "POL-200",
            "totalIncurred": "8000.00",
            "totalPaid": "0.00",
            "deductible": "1000.00",
        },
        {
            "claimId": "GW-003",
            "claimNumber": "CLM-003",
            "lossDate": "2024-05-10",
            "claimState": "closed",
            "reportedDate": "2024-05-11",
            "lossDescription": "Theft",
            "lossCause": "theft",
            "policyNumber": "POL-300",
            "totalIncurred": "15000.00",
            "totalPaid": "15000.00",
            "deductible": "250.00",
        },
    ],
)


class _E2ESemanticMatcher(SemanticMatcher):
    """Maps all Guidewire-style sample fields to universal schema paths."""

    _TARGETS: dict[str, tuple[str, float]] = {
        "lossDate": ("claim.loss_date", 0.9),
        "claimNumber": ("claim.claim_number", 0.95),
        "claimState": ("claim.status", 0.85),
        "reportedDate": ("claim.reported_date", 0.9),
        "lossDescription": ("claim.loss_description", 0.88),
        "lossCause": ("claim.loss_cause", 0.85),
        "policyNumber": ("claim.policy_number", 0.9),
        "totalIncurred": ("claim.total_incurred", 0.9),
        "totalPaid": ("claim.total_paid", 0.9),
        "deductible": ("claim.deductible", 0.88),
        "claimId": ("claim.claim_id", 0.95),
    }

    def __init__(self) -> None:
        pass

    async def match(self, unmatched_fields, already_mapped_targets, **kwargs):  # type: ignore[no-untyped-def]
        del already_mapped_targets, kwargs
        mappings: list[FieldMapping] = []
        for field in unmatched_fields:
            entry = self._TARGETS.get(field.source_name)
            if entry is None:
                continue
            target, confidence = entry
            transform: FieldTransform | None = None
            if field.source_name == "lossDate":
                transform = FieldTransform(
                    transform_type=TransformType.DATE_FORMAT,
                    source_format="YYYY-MM-DD",
                    target_format="ISO 8601",
                )
            elif field.source_name in ("totalPaid", "totalIncurred", "deductible"):
                transform = FieldTransform(
                    transform_type=TransformType.CURRENCY_PARSE,
                    source_format="$#,###.##",
                    target_format="Decimal",
                )
            elif field.source_name == "claimState":
                transform = FieldTransform(
                    transform_type=TransformType.ENUM_MAP,
                    parameters={
                        "enum_name": "ClaimStatus",
                        "enum_map": {"open": "open", "closed": "closed"},
                        "target_field": "claim.status",
                    },
                )
            elif field.source_name == "lossCause":
                transform = FieldTransform(
                    transform_type=TransformType.ENUM_MAP,
                    parameters={
                        "enum_name": "LossCause",
                        "enum_map": {
                            "collision": "collision",
                            "water_damage": "water_damage",
                            "theft": "theft",
                        },
                        "target_field": "claim.loss_cause",
                    },
                )
            mappings.append(
                FieldMapping(
                    source_field=field.source_name,
                    source_path=field.nesting_path,
                    target_field=target,
                    match_type=MatchType.SEMANTIC,
                    confidence=confidence,
                    reasoning="e2e semantic stub",
                    transform=transform,
                ),
            )
        return SemanticMatchOutcome(mappings=mappings, gaps=[])


@pytest.fixture
def e2e_semantic_matcher() -> _E2ESemanticMatcher:
    """Semantic matcher that covers all E2E sample fields."""
    return _E2ESemanticMatcher()


class TestEndToEndPipeline:
    """Full discover -> map -> generate -> transform_batch pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_three_claims(
        self,
        mock_field_analyzer: object,
        e2e_semantic_matcher: _E2ESemanticMatcher,
        tmp_knowledge_base: object,
        tmp_path: Path,
    ) -> None:
        """Sample JSON flows through discovery, mapping, generation, and adapter run."""
        discovery = DiscoveryEngine(
            LLMClient(api_key="test"),
            field_analyzer=mock_field_analyzer,
        )
        profile = await discovery.discover(SAMPLE_JSON, "guidewire_e2e")
        source_names = {f.source_name for f in profile.fields}
        for expected in (
            "lossDate",
            "claimNumber",
            "claimState",
            "claimId",
            "totalPaid",
        ):
            assert expected in source_names

        mapping_engine = MappingEngine(
            LLMClient(api_key="test"),
            tmp_knowledge_base,  # type: ignore[arg-type]
            semantic_matcher=e2e_semantic_matcher,
        )
        config = await mapping_engine.map(profile)
        mapped_sources = {m.source_field for m in config.field_mappings}
        assert len(mapped_sources) >= len(source_names) - 2

        gen_dir = tmp_path / "generated"
        result = GeneratorEngine().generate(config, gen_dir)
        assert result.syntax_valid is True

        registry = AdapterRegistry(registry_path=gen_dir / "registry.json")
        registry.register(result, config)
        adapter_cls = registry.get_adapter_class(config.client_name)
        adapter = adapter_cls()
        batch = adapter.transform_batch(SAMPLE_JSON)

        assert batch.success_count == 3
        assert batch.failure_count == 0
        for claim, _warnings in batch.successful:
            assert claim.claim_number
            assert claim.loss_date.tzinfo is not None
            assert isinstance(claim.status, ClaimStatus)
            assert isinstance(claim.loss_cause, LossCause)
            assert isinstance(claim.line_of_business, LineOfBusiness)
            assert isinstance(claim.total_paid, Decimal)

        for path in gen_dir.glob("*"):
            if path.is_file():
                path.unlink()
        if (gen_dir / "registry.json").exists():
            (gen_dir / "registry.json").unlink()
