"""Semantic matcher tests (mocked LLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.discovery.profile import FieldInfo
from src.exceptions import LLMError
from src.mapping.config import GapType, MatchType
from src.mapping.semantic_matcher import (
    SemanticMatchBatch,
    SemanticMatchResult,
    SemanticMatcher,
)


def _field(name: str, **kwargs: object) -> FieldInfo:
    return FieldInfo(source_name=name, inferred_type="string", **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def mock_llm() -> MagicMock:
    """LLM client with async analyze mock."""
    client = MagicMock()
    client.analyze = AsyncMock()
    return client


class TestSemanticMatcher:
    """SemanticMatcher tests with mocked Gemini."""

    @pytest.mark.asyncio
    async def test_excess_amount_maps_to_deductible(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.return_value = SemanticMatchBatch(
            results=[
                SemanticMatchResult(
                    source_name="excess_amount",
                    target_field="claim.deductible",
                    confidence=0.85,
                    reasoning="excess is deductible",
                )
            ]
        )
        outcome = await SemanticMatcher(mock_llm).match(
            [_field("excess_amount")],
            [],
        )
        assert len(outcome.mappings) == 1
        assert outcome.mappings[0].target_field == "claim.deductible"
        assert outcome.mappings[0].match_type == MatchType.SEMANTIC

    @pytest.mark.asyncio
    async def test_dt_of_lss_maps_to_loss_date(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.return_value = SemanticMatchBatch(
            results=[
                SemanticMatchResult(
                    source_name="dt_of_lss",
                    target_field="claim.loss_date",
                    confidence=0.8,
                    reasoning="DOL synonym",
                )
            ]
        )
        outcome = await SemanticMatcher(mock_llm).match([_field("dt_of_lss")], [])
        assert outcome.mappings[0].target_field == "claim.loss_date"

    @pytest.mark.asyncio
    async def test_null_target_creates_gap(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.return_value = SemanticMatchBatch(
            results=[
                SemanticMatchResult(
                    source_name="alien_field",
                    target_field=None,
                    confidence=0.0,
                    reasoning="no match",
                )
            ]
        )
        outcome = await SemanticMatcher(mock_llm).match([_field("alien_field")], [])
        assert outcome.mappings == []
        assert len(outcome.gaps) == 1
        assert outcome.gaps[0].gap_type == GapType.UNMAPPED_SOURCE

    @pytest.mark.asyncio
    async def test_invalid_target_creates_ambiguous_gap(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.return_value = SemanticMatchBatch(
            results=[
                SemanticMatchResult(
                    source_name="weird",
                    target_field="not.a.real.path",
                    confidence=0.7,
                    reasoning="bad target",
                )
            ]
        )
        outcome = await SemanticMatcher(mock_llm).match([_field("weird")], [])
        assert outcome.mappings == []
        assert outcome.gaps[0].gap_type == GapType.AMBIGUOUS

    @pytest.mark.asyncio
    async def test_batch_15_fields_two_calls(self, mock_llm: MagicMock) -> None:
        fields = [_field(f"f{i}") for i in range(15)]

        async def _side_effect(
            _system: str,
            _user: str,
            _model: type,
        ) -> SemanticMatchBatch:
            import json

            data = json.loads(_user.split(":\n", 1)[-1])
            return SemanticMatchBatch(
                results=[
                    SemanticMatchResult(
                        source_name=item["source_name"],
                        target_field="claim.claim_id",
                        confidence=0.7,
                        reasoning="batch",
                    )
                    for item in data
                ]
            )

        mock_llm.analyze.side_effect = _side_effect
        outcome = await SemanticMatcher(mock_llm).match(fields, [])
        assert mock_llm.analyze.call_count == 2
        assert len(outcome.mappings) >= 1
        assert len(outcome.mappings) + len(outcome.gaps) == 15

    @pytest.mark.asyncio
    async def test_llm_error_propagates(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.side_effect = LLMError("LLM_FAILED", "fail")
        with pytest.raises(LLMError):
            await SemanticMatcher(mock_llm).match([_field("x")], [])

    @pytest.mark.asyncio
    async def test_low_confidence_uses_manual_match_type(self, mock_llm: MagicMock) -> None:
        mock_llm.analyze.return_value = SemanticMatchBatch(
            results=[
                SemanticMatchResult(
                    source_name="uncertain",
                    target_field="claim.claim_id",
                    confidence=0.3,
                    reasoning="guess",
                )
            ]
        )
        outcome = await SemanticMatcher(mock_llm).match([_field("uncertain")], [])
        assert outcome.mappings[0].match_type == MatchType.MANUAL
