"""Gemini-powered adversarial edge case generation and execution."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.exceptions import LLMError
from src.llm.client import LLMClient
from src.schema.base_adapter import BaseAdapter
from src.testing.codes import TEST_EDGE_GENERATION_FAILED

ExpectedBehavior = Literal["should_succeed", "should_fail", "should_warn"]


class EdgeCase(BaseModel):
    """Single adversarial test case."""

    model_config = ConfigDict(strict=True)

    name: str
    category: str
    mutated_record: dict[str, object] | str
    mutation_description: str
    expected_behavior: ExpectedBehavior


class EdgeCaseList(BaseModel):
    """Wrapper for LLM structured output."""

    model_config = ConfigDict(strict=True)

    cases: list[EdgeCase]


class EdgeCaseGenerator:
    """Generates adversarial inputs via Gemini."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def generate(
        self,
        adapter_name: str,
        source_format: str,
        sample_record: dict[str, object] | str,
        count: int = 20,
    ) -> list[EdgeCase]:
        """Generate edge cases for an adapter format."""
        sample_text = (
            sample_record
            if isinstance(sample_record, str)
            else json.dumps(sample_record, indent=2)
        )
        system = (
            "You are a QA engineer testing insurance claims data adapters. "
            "Return JSON matching the schema with adversarial test cases."
        )
        user = f"""Adapter: {adapter_name}
Source format: {source_format}
Generate {count} adversarial test cases from this sample:

{sample_text}

Categories: nulls, boundary dates, boundary amounts, unicode, format violations,
missing required fields, extra fields, type mismatches, duplicate IDs, bad FKs.
Each case needs name, category, mutated_record, mutation_description, expected_behavior
(one of should_succeed, should_fail, should_warn)."""
        try:
            result = await self._llm.analyze(
                system,
                user,
                EdgeCaseList,
                temperature=0.2,
            )
        except LLMError as exc:
            raise LLMError(
                TEST_EDGE_GENERATION_FAILED,
                f"Edge case generation failed: {exc.message}",
                details=exc.details,
            ) from exc
        return result.cases[:count]


class EdgeCaseRunner:
    """Executes edge cases against an adapter."""

    def run_case(
        self,
        adapter: BaseAdapter,
        edge_case: EdgeCase,
        source_format: str,
    ) -> str:
        """Return passed, failed_expected, or failed_unexpected."""
        raw_input = self._wrap_input(edge_case.mutated_record, source_format)
        try:
            result = adapter.transform_batch(raw_input)
            succeeded = result.success_count > 0 and result.failure_count == 0
            warned = any(w for _c, w in result.successful for w in w)
        except Exception:
            succeeded = False
            warned = False

        expected = edge_case.expected_behavior
        if expected == "should_fail":
            return "passed" if not succeeded else "failed_unexpected"
        if expected == "should_warn":
            return "passed" if succeeded else "failed_unexpected"
        if expected == "should_succeed":
            return "passed" if succeeded and not warned else "failed_unexpected"
        return "failed_unexpected"

    @staticmethod
    def _wrap_input(record: dict[str, object] | str, source_format: str) -> str | bytes:
        fmt = source_format.lower()
        if fmt == "json":
            if isinstance(record, str):
                return record
            if isinstance(record, list):
                return json.dumps(record)
            return json.dumps([record])
        if fmt == "xml":
            if isinstance(record, str):
                return record
            return (
                '<?xml version="1.0"?><ClaimsSvcRq><ClaimsOccurrence>'
                + "".join(f"<{k}>{v}</{k}>" for k, v in record.items())
                + "</ClaimsOccurrence></ClaimsSvcRq>"
            )
        if fmt == "csv":
            if isinstance(record, str):
                return record
            return "|".join(str(v) for v in record.values())
        return json.dumps(record) if isinstance(record, dict) else str(record)
