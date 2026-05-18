"""Google Gemini LLM client with structured output validation."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.config import get_settings
from src.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Async wrapper around the Gemini API for structured LLM responses."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Initialize client with optional overrides for testing."""
        settings = get_settings()
        key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model or settings.gemini_model_discovery
        self._client = genai.Client(api_key=key)

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
        temperature: float = 0.0,
    ) -> T:
        """Call Gemini and validate response against a Pydantic model."""
        prompt_hash = hashlib.sha256(
            (system_prompt + user_prompt).encode("utf-8")
        ).hexdigest()[:16]
        last_error: str | None = None
        for attempt in range(2):
            start = time.perf_counter()
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(text=f"{system_prompt}\n\n{user_prompt}"),
                            ],
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=output_model,
                    ),
                )
                latency_ms = (time.perf_counter() - start) * 1000
                usage = getattr(response, "usage_metadata", None)
                token_count = getattr(usage, "total_token_count", 0) if usage else 0
                parsed = response.parsed
                if parsed is None and response.text:
                    parsed = json.loads(response.text)
                result = output_model.model_validate(parsed)
                logger.info(
                    "LLM call succeeded hash=%s tokens=%s latency_ms=%.1f attempt=%s",
                    prompt_hash,
                    token_count,
                    latency_ms,
                    attempt + 1,
                )
                return result
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = str(exc)
                logger.warning(
                    "LLM validation failed hash=%s latency_ms=%.1f attempt=%s error=%s",
                    prompt_hash,
                    latency_ms,
                    attempt + 1,
                    last_error,
                )
                user_prompt = f"{user_prompt}\n\nPrevious response failed validation: {last_error}"
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "LLM call failed hash=%s latency_ms=%.1f error=%s",
                    prompt_hash,
                    latency_ms,
                    exc,
                )
                raise LLMError(
                    "LLM_REQUEST_FAILED",
                    f"Gemini API call failed: {exc}",
                    details={"prompt_hash": prompt_hash},
                ) from exc
        raise LLMError(
            "LLM_VALIDATION_FAILED",
            "LLM response failed validation after retry",
            details={"prompt_hash": prompt_hash, "last_error": last_error},
        )
