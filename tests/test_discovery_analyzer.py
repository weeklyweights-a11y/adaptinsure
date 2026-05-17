"""Tests for InsuranceFieldAnalyzer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.discovery.analyzer import FieldAnnotationBatch, FieldAnnotationItem, InsuranceFieldAnalyzer
from src.discovery.profile import FieldInfo
from src.llm.client import LLMClient


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """LLM client that returns deterministic annotations."""
    client = AsyncMock(spec=LLMClient)
    call_count = 0

    async def analyze(system_prompt: str, user_prompt: str, output_model: type) -> FieldAnnotationBatch:
        nonlocal call_count
        call_count += 1
        client.call_count = call_count
        del system_prompt
        if "lossDate" in user_prompt:
            return FieldAnnotationBatch(
                fields=[
                    FieldAnnotationItem(
                        source_name="lossDate",
                        insurance_annotation="date of loss",
                        confidence=0.95,
                    )
                ]
            )
        import json

        data = json.loads(user_prompt)
        fields = data.get("fields", [])
        return FieldAnnotationBatch(
            fields=[
                FieldAnnotationItem(
                    source_name=f["source_name"],
                    insurance_annotation=f"meaning of {f['source_name']}",
                    confidence=0.8,
                )
                for f in fields
            ]
        )

    client.analyze = AsyncMock(side_effect=analyze)
    client.call_count = 0
    return client


@pytest.mark.asyncio
async def test_clear_insurance_names_annotated(
    mock_llm_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fields with clear insurance names get annotations."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    analyzer = InsuranceFieldAnalyzer(mock_llm_client)
    fields = [FieldInfo(source_name="lossDate", inferred_type="date")]
    result = await analyzer.annotate_fields(fields, "json", [])
    assert result[0].insurance_annotation == "date of loss"


@pytest.mark.asyncio
async def test_chunking_over_forty_fields(
    mock_llm_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """More than 40 fields are processed in chunks."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    analyzer = InsuranceFieldAnalyzer(mock_llm_client)
    fields = [
        FieldInfo(source_name=f"field_{i}", inferred_type="string") for i in range(45)
    ]
    result = await analyzer.annotate_fields(fields, "json", [])
    assert len(result) == 45
    assert mock_llm_client.call_count >= 2


@pytest.mark.asyncio
async def test_output_count_matches_input(
    mock_llm_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Field count in output matches input."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    analyzer = InsuranceFieldAnalyzer(mock_llm_client)
    fields = [
        FieldInfo(source_name="a", inferred_type="string"),
        FieldInfo(source_name="b", inferred_type="string"),
    ]
    result = await analyzer.annotate_fields(fields, "json", [])
    assert len(result) == 2
