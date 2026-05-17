"""Shared pytest fixtures and session configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.config import setup_logging
from src.schema.base_adapter import BaseAdapter
from src.schema.enums import (
    ClaimStatus,
    ContactRole,
    ExposureStatus,
    ExposureType,
    LineOfBusiness,
    LossCause,
    TransactionStatus,
    TransactionType,
)
from src.schema.models import (
    Address,
    Claim,
    Claimant,
    Coverage,
    Exposure,
    PolicySnapshot,
    Transaction,
)
def pytest_configure(config: pytest.Config) -> None:
    """Initialize logging before any tests run."""
    setup_logging()


UTC = timezone.utc


@pytest.fixture
def valid_address() -> Address:
    """Valid US address."""
    return Address(
        street_1="123 Main St",
        city="Newark",
        state="NJ",
        postal_code="07302",
        country="US",
    )


@pytest.fixture
def valid_policy(valid_address: Address) -> PolicySnapshot:
    """Valid policy snapshot with coverages."""
    return PolicySnapshot(
        policy_number="POL-100",
        carrier_name="Example Carrier",
        product_type="Personal Auto",
        effective_date=datetime(2024, 1, 1, tzinfo=UTC),
        expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
        insured_name="Jane Doe",
        coverages=[
            Coverage(
                coverage_type="Collision",
                limit=Decimal("50000"),
                deductible=Decimal("500"),
                premium=Decimal("1200"),
            )
        ],
        premium=Decimal("1200"),
    )


@pytest.fixture
def valid_claim(valid_address: Address) -> Claim:
    """Fully populated claim with nested entities."""
    claim_id = "CLM-001"
    return Claim(
        claim_id=claim_id,
        claim_number="2024-0001",
        status=ClaimStatus.OPEN,
        loss_date=datetime(2024, 3, 1, 12, 0, tzinfo=UTC),
        reported_date=datetime(2024, 3, 2, 9, 0, tzinfo=UTC),
        loss_description="Rear-end collision",
        loss_cause=LossCause.COLLISION,
        loss_location=valid_address,
        line_of_business=LineOfBusiness.PERSONAL_AUTO,
        policy_number="POL-100",
        policy_effective_date=datetime(2024, 1, 1, tzinfo=UTC),
        policy_expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
        total_incurred=Decimal("15000"),
        total_paid=Decimal("5000"),
        total_reserved=Decimal("10000"),
        deductible=Decimal("500"),
        created_at=datetime(2024, 3, 2, 10, 0, tzinfo=UTC),
        updated_at=datetime(2024, 3, 2, 10, 0, tzinfo=UTC),
        source_system="test_carrier",
        raw_data={"source": "fixture"},
        exposures=[
            Exposure(
                exposure_id="EXP-1",
                claim_id=claim_id,
                exposure_type=ExposureType.VEHICLE_DAMAGE,
                coverage_type="Collision",
                status=ExposureStatus.OPEN,
                reserved_amount=Decimal("8000"),
                paid_amount=Decimal("3000"),
                deductible_amount=Decimal("500"),
                claimant_id="CLMT-1",
            ),
            Exposure(
                exposure_id="EXP-2",
                claim_id=claim_id,
                exposure_type=ExposureType.BODILY_INJURY,
                coverage_type="BI",
                reserved_amount=Decimal("7000"),
                paid_amount=Decimal("2000"),
                deductible_amount=Decimal("0"),
                claimant_id="CLMT-2",
            ),
        ],
        claimants=[
            Claimant(
                claimant_id="CLMT-1",
                claim_id=claim_id,
                role=ContactRole.CLAIMANT,
                first_name="John",
                last_name="Driver",
            ),
            Claimant(
                claimant_id="CLMT-2",
                claim_id=claim_id,
                role=ContactRole.INSURED,
                first_name="Jane",
                last_name="Doe",
            ),
        ],
        transactions=[
            Transaction(
                transaction_id="TXN-1",
                claim_id=claim_id,
                exposure_id="EXP-1",
                transaction_type=TransactionType.PAYMENT,
                amount=Decimal("3000"),
                transaction_date=datetime(2024, 3, 10, tzinfo=UTC),
                status=TransactionStatus.POSTED,
            ),
            Transaction(
                transaction_id="TXN-2",
                claim_id=claim_id,
                exposure_id="EXP-2",
                transaction_type=TransactionType.RESERVE_SET,
                amount=Decimal("7000"),
                transaction_date=datetime(2024, 3, 5, tzinfo=UTC),
            ),
            Transaction(
                transaction_id="TXN-3",
                claim_id=claim_id,
                transaction_type=TransactionType.RECOVERY,
                amount=Decimal("-500"),
                transaction_date=datetime(2024, 3, 15, tzinfo=UTC),
            ),
        ],
    )


class MockAdapter(BaseAdapter):
    """Minimal adapter for testing transform_batch."""

    @property
    def name(self) -> str:
        return "Mock Test Adapter"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def source_system(self) -> str:
        return "mock"

    @property
    def supported_formats(self) -> list[str]:
        return ["json"]

    def parse_raw(self, raw_input: str | bytes) -> list[dict[str, object]]:
        """Parse JSON array or single object into raw records."""
        text = raw_input.decode() if isinstance(raw_input, bytes) else raw_input
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return [data]

    def map_record(self, raw_record: dict[str, object]) -> dict[str, object]:
        """Pass through mapped records (already universal shape in tests)."""
        return raw_record


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Mock adapter instance."""
    return MockAdapter()


def claim_to_mapped_dict(claim: Claim) -> dict[str, object]:
    """Serialize claim to dict for adapter tests (Python mode for strict validation)."""
    return claim.model_dump()
