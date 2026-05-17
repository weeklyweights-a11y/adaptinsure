"""Tests for the Gemini LLM client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from src.exceptions import LLMError
from src.llm.client import LLMClient


class SampleOutput(BaseModel):
    """Sample structured output model."""

    model_config = ConfigDict(strict=True)

    answer: str


@pytest.mark.asyncio
async def test_analyze_returns_validated_model() -> None:
    """Successful API call returns validated Pydantic model."""
    mock_response = MagicMock()
    mock_response.parsed = {"answer": "ok"}
    mock_response.text = None
    mock_response.usage_metadata = MagicMock(total_token_count=42)

    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch("src.llm.client.genai.Client", return_value=mock_client):
        client = LLMClient(api_key="test-key")
        result = await client.analyze("sys", "user", SampleOutput)
    assert result.answer == "ok"


@pytest.mark.asyncio
async def test_analyze_retries_once_on_validation_failure() -> None:
    """Invalid response triggers one retry then succeeds."""
    bad = MagicMock()
    bad.parsed = {"wrong": "field"}
    bad.text = None
    bad.usage_metadata = MagicMock(total_token_count=10)

    good = MagicMock()
    good.parsed = {"answer": "retry ok"}
    good.text = None
    good.usage_metadata = MagicMock(total_token_count=20)

    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(side_effect=[bad, good])
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch("src.llm.client.genai.Client", return_value=mock_client):
        client = LLMClient(api_key="test-key")
        result = await client.analyze("sys", "user", SampleOutput)
    assert result.answer == "retry ok"
    assert mock_aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_analyze_raises_llm_error_after_double_failure() -> None:
    """Two validation failures raise LLMError."""
    bad = MagicMock()
    bad.parsed = {"wrong": "field"}
    bad.text = None
    bad.usage_metadata = MagicMock(total_token_count=5)

    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=bad)
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with (
        patch("src.llm.client.genai.Client", return_value=mock_client),
        pytest.raises(LLMError) as exc_info,
    ):
        client = LLMClient(api_key="test-key")
        await client.analyze("sys", "user", SampleOutput)
    assert exc_info.value.error_code == "LLM_VALIDATION_FAILED"
