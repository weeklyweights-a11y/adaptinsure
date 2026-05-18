"""Mock adapters for contract test scenarios."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.schema.base_adapter import BaseAdapter
from src.schema.enums import ClaimStatus, LineOfBusiness, LossCause
from src.schema.models import Address, Claim

UTC = timezone.utc


def _base_claim(**overrides: object) -> Claim:
    claim_id = str(overrides.get("claim_id", "MOCK-001"))
    now = datetime.now(tz=UTC)
    data = {
        "claim_id": claim_id,
        "claim_number": str(overrides.get("claim_number", "CLM-MOCK-001")),
        "status": overrides.get("status", ClaimStatus.OPEN),
        "loss_date": overrides.get("loss_date", now - timedelta(days=5)),
        "reported_date": overrides.get("reported_date", now - timedelta(days=4)),
        "closed_date": overrides.get("closed_date"),
        "loss_description": overrides.get("loss_description", "Test loss"),
        "loss_cause": overrides.get("loss_cause", LossCause.COLLISION),
        "loss_location": overrides.get(
            "loss_location",
            Address(
                street_1="1 Main",
                city="Columbus",
                state="OH",
                postal_code="43215",
            ),
        ),
        "line_of_business": overrides.get("line_of_business", LineOfBusiness.PERSONAL_AUTO),
        "policy_number": "POL-1",
        "policy_effective_date": datetime(2024, 1, 1, tzinfo=UTC),
        "policy_expiration_date": datetime(2025, 1, 1, tzinfo=UTC),
        "total_incurred": overrides.get("total_incurred", Decimal("1000")),
        "total_paid": overrides.get("total_paid", Decimal("100")),
        "total_reserved": overrides.get("total_reserved", Decimal("900")),
        "deductible": Decimal("500"),
        "created_at": now,
        "updated_at": now,
        "source_system": "mock",
        "raw_data": {},
        "exposures": overrides.get("exposures", []),
        "claimants": overrides.get("claimants", []),
        "transactions": overrides.get("transactions", []),
    }
    try:
        return Claim.model_validate(data)
    except Exception:
        return Claim.model_construct(**data)  # type: ignore[arg-type]


class ContractTestMockAdapter(BaseAdapter):
    """Returns predetermined claims for contract harness tests."""

    def __init__(self, claims: list[Claim] | None = None) -> None:
        self._claims = claims or [_base_claim()]

    @property
    def name(self) -> str:
        return "Contract Test Mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def source_system(self) -> str:
        return "mock_contract"

    @property
    def supported_formats(self) -> list[str]:
        return ["json"]

    def parse_raw(self, raw_input: str | bytes) -> list[dict[str, object]]:
        text = raw_input.decode() if isinstance(raw_input, bytes) else raw_input
        data = json.loads(text)
        return data if isinstance(data, list) else [data]

    def map_record(self, raw_record: dict[str, object]) -> dict[str, object]:
        return raw_record

    def validate_record(self, mapped_record: dict[str, object]):  # type: ignore[no-untyped-def]
        return Claim.model_validate(mapped_record), []

    def transform_batch(self, raw_input: str | bytes):  # type: ignore[no-untyped-def]
        from src.schema.base_adapter import TransformResult

        result = TransformResult()
        for claim in self._claims:
            result.successful.append((claim, []))
        result.total_records = len(self._claims)
        result.success_count = len(self._claims)
        return result
