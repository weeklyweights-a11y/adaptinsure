"""Tests for BaseAdapter and TransformResult."""

from __future__ import annotations

import json

import pytest

from src.exceptions import MappingError, SchemaValidationError
from src.schema import BaseAdapter, TransformResult
from tests.conftest import MockAdapter


class TestBaseAdapter:
    """BaseAdapter ABC and transform_batch behavior."""

    def test_base_adapter_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            BaseAdapter()  # type: ignore[abstract]

    def test_mock_adapter_can_be_instantiated(self, mock_adapter: MockAdapter) -> None:
        assert mock_adapter.name == "Mock Test Adapter"

    def test_transform_batch_returns_transform_result(
        self,
        mock_adapter: MockAdapter,
        valid_claim,
    ) -> None:
        payload = f"[{valid_claim.model_dump_json()}]"
        result = mock_adapter.transform_batch(payload)
        assert isinstance(result, TransformResult)

    def test_transform_batch_success_path(
        self,
        mock_adapter: MockAdapter,
        valid_claim,
    ) -> None:
        payload = f"[{valid_claim.model_dump_json()}]"
        result = mock_adapter.transform_batch(payload)
        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.total_records == 1
        assert len(result.successful) == 1

    def test_transform_batch_continues_after_failure(
        self,
        mock_adapter: MockAdapter,
        valid_claim,
    ) -> None:
        good_json = valid_claim.model_dump_json()
        bad = {"claim_id": "BAD"}
        payload = json.dumps([bad, json.loads(good_json)])
        result = mock_adapter.transform_batch(payload)
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.total_records == 2

    def test_transform_batch_counts_sum_to_total(
        self,
        mock_adapter: MockAdapter,
        valid_claim,
    ) -> None:
        payload = f"[{valid_claim.model_dump_json()}]"
        result = mock_adapter.transform_batch(payload)
        assert result.success_count + result.failure_count == result.total_records


class FailingMapAdapter(MockAdapter):
    """Adapter that fails mapping for specific records."""

    def map_record(self, raw_record: dict[str, object]) -> dict[str, object]:
        if raw_record.get("claim_id") == "FAIL":
            raise MappingError("MAP_FAIL", "mapping failed")
        return super().map_record(raw_record)


class TestFailingMapAdapter:
    """Partial failure collection tests."""

    def test_transform_batch_collects_mapping_errors(
        self,
        valid_claim,
    ) -> None:
        adapter = FailingMapAdapter()
        good = json.loads(valid_claim.model_dump_json())
        payload = json.dumps([{"claim_id": "FAIL"}, good])
        result = adapter.transform_batch(payload)
        assert result.failure_count == 1
        assert isinstance(result.failed[0][1], MappingError)
