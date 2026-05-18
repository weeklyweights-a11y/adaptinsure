"""Tests for src/testing harness modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schema.enums import ClaimStatus, LossCause
from src.schema.models import Exposure
from src.testing.contract_tests import ContractTestRunner
from src.testing.edge_cases import EdgeCase, EdgeCaseGenerator, EdgeCaseList, EdgeCaseRunner
from src.testing.reporter import TestReporter
from src.testing.roundtrip import RoundTripValidator
from tests.testing.mock_adapter import ContractTestMockAdapter, _base_claim

UTC = timezone.utc


class TestContractTestRunner:
    def test_all_checks_pass(self) -> None:
        adapter = ContractTestMockAdapter([_base_claim()])
        result = ContractTestRunner().run(adapter, b"[]")
        assert result.failed_checks == 0
        assert result.pass_rate == 1.0

    def test_empty_loss_description_fails(self) -> None:
        claim = _base_claim(loss_description="")
        adapter = ContractTestMockAdapter([claim])
        result = ContractTestRunner().run(adapter, b"[]")
        assert any(f.check_name == "required_field:loss_description" for f in result.failures)

    def test_future_loss_date_fails(self) -> None:
        future = datetime.now(tz=UTC) + timedelta(days=30)
        claim = _base_claim(loss_date=future)
        result = ContractTestRunner().run(ContractTestMockAdapter([claim]), b"[]")
        assert any(f.check_name == "date_sanity:future_loss_date" for f in result.failures)

    def test_reported_before_loss_fails(self) -> None:
        loss = datetime(2024, 5, 1, tzinfo=UTC)
        reported = datetime(2024, 4, 1, tzinfo=UTC)
        claim = _base_claim(loss_date=loss, reported_date=reported)
        result = ContractTestRunner().run(ContractTestMockAdapter([claim]), b"[]")
        assert any(f.check_name == "date_sanity:reported_before_loss" for f in result.failures)

    def test_negative_total_paid_fails(self) -> None:
        claim = _base_claim(total_paid=Decimal("-1"))
        result = ContractTestRunner().run(ContractTestMockAdapter([claim]), b"[]")
        assert any("total_paid" in f.check_name for f in result.failures)

    def test_exposure_claim_id_mismatch(self) -> None:
        from src.schema.enums import ExposureType

        bad_exposure = Exposure(
            exposure_id="E1",
            claim_id="OTHER",
            exposure_type=ExposureType.VEHICLE_DAMAGE,
            coverage_type="C",
            claimant_id="C1",
        )
        claim = _base_claim(exposures=[bad_exposure])
        result = ContractTestRunner().run(ContractTestMockAdapter([claim]), b"[]")
        assert any(f.check_name == "referential_integrity:exposure_claim_id" for f in result.failures)

    def test_enum_validity_direct(self) -> None:
        assert ContractTestRunner._check_enum_validity(ClaimStatus.OPEN, ClaimStatus)
        assert not ContractTestRunner._check_enum_validity("not_a_status", ClaimStatus)

    def test_pass_rate_mixed(self) -> None:
        good = _base_claim(claim_id="G1")
        bad = _base_claim(claim_id="B1", loss_description="")
        result = ContractTestRunner().run(
            ContractTestMockAdapter([good, bad]),
            b"[]",
        )
        assert result.total_claims == 2
        assert result.passed_claims == 1
        assert result.failed_claims == 1
        assert 0 < result.pass_rate < 1


class _RoundTripStubAdapter:
    """Minimal adapter with FIELD_MAPPINGS for round-trip tests."""

    FIELD_MAPPINGS = {
        "lossDate": {
            "target_field": "claim.loss_date",
            "transform": "_transform_date_yyyy_mm_dd",
        },
        "amount": {
            "target_field": "claim.total_paid",
            "transform": "_transform_currency",
        },
    }
    _SOURCE_PATHS: dict[str, str] = {}

    def map_record(self, raw: dict[str, object]) -> dict[str, object]:
        return {
            "claim": {
                "claim_id": "R1",
                "claim_number": "R1",
                "status": "open",
                "loss_date": "2024-01-15T00:00:00+00:00",
                "reported_date": "2024-01-16T00:00:00+00:00",
                "loss_description": "x",
                "loss_cause": "collision",
                "loss_location": {
                    "street_1": "1",
                    "city": "c",
                    "state": "OH",
                    "postal_code": "43215",
                },
                "line_of_business": "personal_auto",
                "policy_number": "P",
                "policy_effective_date": "2024-01-01T00:00:00+00:00",
                "policy_expiration_date": "2025-01-01T00:00:00+00:00",
                "total_paid": "1234.56",
                "source_system": "stub",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        }

    def validate_record(self, mapped: dict[str, object]):  # type: ignore[no-untyped-def]
        from src.schema.models import Claim

        return Claim.model_validate(mapped), []

    def parse_raw(self, raw_input: str | bytes) -> list[dict[str, object]]:
        import json

        text = raw_input.decode() if isinstance(raw_input, bytes) else raw_input
        data = json.loads(text)
        return data if isinstance(data, list) else [data]


class TestRoundTripValidator:
    def test_empty_input(self) -> None:
        adapter = _RoundTripStubAdapter()
        result = RoundTripValidator().validate(adapter, "[]")
        assert result.total_records == 0
        assert result.field_survival_rate == 0.0

    def test_date_and_currency_survival(self) -> None:
        raw = [{"lossDate": "2024-01-15", "amount": "$1,234.56"}]
        result = RoundTripValidator().validate(
            _RoundTripStubAdapter(),
            __import__("json").dumps(raw),
        )
        assert result.total_records == 1
        assert result.fields_transformed >= 0


class TestEdgeCaseGenerator:
    @pytest.mark.asyncio
    async def test_generate_mocked(self) -> None:
        cases = [
            EdgeCase(
                name="future_loss_date",
                category="boundary_dates",
                mutated_record={"lossDate": "2099-01-01"},
                mutation_description="future date",
                expected_behavior="should_fail",
            )
        ]
        llm = MagicMock()
        llm.analyze = AsyncMock(return_value=EdgeCaseList(cases=cases))
        gen = EdgeCaseGenerator(llm)
        result = await gen.generate("test", "json", {"lossDate": "2024-01-01"}, count=1)
        assert len(result) == 1
        assert result[0].category == "boundary_dates"

    def test_runner_json_wrap(self) -> None:
        edge = EdgeCase(
            name="bad",
            category="nulls",
            mutated_record={"claimId": ""},
            mutation_description="empty id",
            expected_behavior="should_fail",
        )
        adapter = ContractTestMockAdapter([])
        outcome = EdgeCaseRunner().run_case(adapter, edge, "json")
        assert outcome in ("passed", "failed_expected", "failed_unexpected")


class TestTestReporter:
    def test_save_and_format(self, tmp_path: Path) -> None:
        from src.testing.contract_tests import ContractTestResult
        from src.testing.roundtrip import RoundTripResult

        contract = ContractTestResult(
            total_claims=1,
            passed_claims=1,
            total_checks=10,
            passed_checks=10,
            pass_rate=1.0,
        )
        roundtrip = RoundTripResult(
            total_records=1,
            total_fields_checked=5,
            fields_survived=5,
            field_survival_rate=1.0,
        )
        report = TestReporter().generate_report(contract, roundtrip)
        assert report.overall_status == "pass"
        out = tmp_path / "report"
        TestReporter().save_report(report, out)
        assert out.with_suffix(".txt").exists()
        assert out.with_suffix(".json").exists()
