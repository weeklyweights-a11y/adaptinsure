"""Full pipeline integration tests against synthetic insurer samples."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.testing.pipeline_helpers import run_insurer_pipeline
from tests.testing.semantic_stubs import (
    acord_semantic_matcher,
    guidewire_semantic_matcher,
    legacy_semantic_matcher,
)

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
REPORTS = Path(__file__).resolve().parent / "reports"


@pytest.mark.integration
class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_guidewire(
        self,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
        tmp_path: Path,
    ) -> None:
        gen_dir = tmp_path / "gen_gw"
        result = await run_insurer_pipeline(
            sample_path=SAMPLES / "guidewire_carrier" / "sample_claims.json",
            client_name="guidewire_carrier",
            source_format="json",
            semantic_matcher=guidewire_semantic_matcher(),
            mock_field_analyzer=mock_field_analyzer,
            tmp_knowledge_base=tmp_knowledge_base,
            gen_dir=gen_dir,
            reports_dir=REPORTS,
            expected_count=15,
            contract_threshold=0.95,
            survival_threshold=0.90,
            extra_discover_path=SAMPLES / "guidewire_carrier" / "api_spec.json",
        )
        assert result.generation_syntax_valid

    @pytest.mark.asyncio
    async def test_full_pipeline_acord(
        self,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
        tmp_path: Path,
    ) -> None:
        gen_dir = tmp_path / "gen_acord"
        result = await run_insurer_pipeline(
            sample_path=SAMPLES / "acord_carrier" / "sample_claims.xml",
            client_name="acord_carrier",
            source_format="xml",
            semantic_matcher=acord_semantic_matcher(),
            mock_field_analyzer=mock_field_analyzer,
            tmp_knowledge_base=tmp_knowledge_base,
            gen_dir=gen_dir,
            reports_dir=REPORTS,
            expected_count=12,
            contract_threshold=0.90,
            survival_threshold=0.85,
        )
        assert result.generation_syntax_valid

    @pytest.mark.asyncio
    async def test_full_pipeline_legacy(
        self,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
        tmp_path: Path,
    ) -> None:
        from src.testing.legacy_bundler import load_legacy_bundle

        bundle = load_legacy_bundle(SAMPLES)
        gen_dir = tmp_path / "gen_legacy"
        result = await run_insurer_pipeline(
            sample_path=SAMPLES / "legacy_carrier" / "claims.csv",
            client_name="legacy_carrier",
            source_format="csv",
            semantic_matcher=legacy_semantic_matcher(),
            mock_field_analyzer=mock_field_analyzer,
            tmp_knowledge_base=tmp_knowledge_base,
            gen_dir=gen_dir,
            reports_dir=REPORTS,
            expected_count=20,
            contract_threshold=0.85,
            survival_threshold=0.80,
            data_dictionary=bundle.data_dictionary_text,
            legacy_bundle=bundle,
        )
        assert result.generation_syntax_valid
