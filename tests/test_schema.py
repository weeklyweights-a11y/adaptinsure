"""Tests for schema enums and Pydantic models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schema import (
    Address,
    Claim,
    Claimant,
    ClaimStatus,
    ContactRole,
    Coverage,
    Exposure,
    ExposureStatus,
    ExposureType,
    LineOfBusiness,
    LossCause,
    PolicySnapshot,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from tests.conftest import UTC

ENUM_COUNTS = {
    ClaimStatus: 5,
    ExposureStatus: 2,
    ExposureType: 9,
    ContactRole: 7,
    TransactionType: 4,
    TransactionStatus: 4,
    LineOfBusiness: 10,
    LossCause: 11,
}


class TestEnums:
    """Enum value and serialization tests."""

    @pytest.mark.parametrize(
        ("enum_cls", "expected_count"),
        list(ENUM_COUNTS.items()),
    )
    def test_enum_has_expected_value_count(self, enum_cls: type, expected_count: int) -> None:
        assert len(enum_cls) == expected_count

    @pytest.mark.parametrize("enum_cls", list(ENUM_COUNTS.keys()))
    def test_enum_values_are_strings(self, enum_cls: type) -> None:
        for member in enum_cls:
            assert isinstance(member.value, str)

    def test_claim_status_from_string_succeeds(self) -> None:
        assert ClaimStatus("open") == ClaimStatus.OPEN

    def test_claim_status_invalid_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            ClaimStatus("invalid")

    def test_enum_json_roundtrip(self) -> None:
        status = ClaimStatus.OPEN
        assert json.loads(json.dumps(status.value)) == status.value


class TestAddress:
    """Address model tests."""

    def test_address_valid_us_succeeds(self, valid_address: Address) -> None:
        assert valid_address.country == "US"

    def test_address_international_succeeds(self) -> None:
        addr = Address(
            street_1="10 Downing St",
            city="London",
            state="England",
            postal_code="SW1A",
            country="GB",
        )
        assert addr.country == "GB"

    def test_address_missing_city_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Address(street_1="1 St", state="NJ", postal_code="07000")

    def test_address_postal_code_keeps_leading_zero(self) -> None:
        addr = Address(street_1="1 St", city="Jersey City", state="NJ", postal_code="07302")
        assert addr.postal_code == "07302"
        assert isinstance(addr.postal_code, str)


class TestCoverage:
    """Coverage model tests."""

    def test_coverage_valid_succeeds(self) -> None:
        cov = Coverage(
            coverage_type="Collision",
            limit=Decimal("10000"),
            deductible=Decimal("500"),
            premium=Decimal("200"),
        )
        assert cov.limit == Decimal("10000")

    def test_coverage_negative_limit_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Coverage(
                coverage_type="Collision",
                limit=Decimal("-1"),
                deductible=Decimal("0"),
                premium=Decimal("0"),
            )

    def test_coverage_negative_deductible_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Coverage(
                coverage_type="Collision",
                limit=Decimal("100"),
                deductible=Decimal("-1"),
                premium=Decimal("0"),
            )

    def test_coverage_negative_premium_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Coverage(
                coverage_type="Collision",
                limit=Decimal("100"),
                deductible=Decimal("0"),
                premium=Decimal("-1"),
            )

    def test_coverage_decimal_precision_maintained(self) -> None:
        cov = Coverage(
            coverage_type="Collision",
            limit=Decimal("1234.56"),
            deductible=Decimal("0"),
            premium=Decimal("0"),
        )
        assert cov.limit == Decimal("1234.56")


class TestClaim:
    """Claim model tests."""

    def test_claim_valid_full_succeeds(self, valid_claim: Claim) -> None:
        assert valid_claim.claim_id == "CLM-001"

    def test_claim_minimal_required_succeeds(self, valid_address: Address) -> None:
        claim = Claim(
            claim_id="CLM-MIN",
            claim_number="MIN-1",
            status=ClaimStatus.OPEN,
            loss_date=datetime(2024, 1, 1, tzinfo=UTC),
            reported_date=datetime(2024, 1, 1, tzinfo=UTC),
            loss_description="Test",
            loss_cause=LossCause.OTHER,
            loss_location=valid_address,
            line_of_business=LineOfBusiness.OTHER,
            policy_number="P1",
            policy_effective_date=datetime(2024, 1, 1, tzinfo=UTC),
            policy_expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            source_system="test",
        )
        assert claim.closed_date is None

    def test_claim_reported_before_loss_raises_validation_error(
        self,
        valid_address: Address,
    ) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="CLM-BAD",
                claim_number="BAD",
                status=ClaimStatus.OPEN,
                loss_date=datetime(2024, 3, 5, tzinfo=UTC),
                reported_date=datetime(2024, 3, 1, tzinfo=UTC),
                loss_description="Test",
                loss_cause=LossCause.OTHER,
                loss_location=valid_address,
                line_of_business=LineOfBusiness.OTHER,
                policy_number="P1",
                policy_effective_date=datetime(2024, 1, 1, tzinfo=UTC),
                policy_expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                updated_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_system="test",
            )

    def test_claim_closed_before_reported_raises_validation_error(
        self,
        valid_address: Address,
    ) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="CLM-BAD",
                claim_number="BAD",
                status=ClaimStatus.CLOSED,
                loss_date=datetime(2024, 3, 1, tzinfo=UTC),
                reported_date=datetime(2024, 3, 5, tzinfo=UTC),
                closed_date=datetime(2024, 3, 4, tzinfo=UTC),
                loss_description="Test",
                loss_cause=LossCause.OTHER,
                loss_location=valid_address,
                line_of_business=LineOfBusiness.OTHER,
                policy_number="P1",
                policy_effective_date=datetime(2024, 1, 1, tzinfo=UTC),
                policy_expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                updated_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_system="test",
            )

    def test_claim_policy_expiration_before_effective_raises_validation_error(
        self,
        valid_address: Address,
    ) -> None:
        with pytest.raises(ValidationError):
            Claim(
                claim_id="CLM-BAD",
                claim_number="BAD",
                status=ClaimStatus.OPEN,
                loss_date=datetime(2024, 3, 1, tzinfo=UTC),
                reported_date=datetime(2024, 3, 2, tzinfo=UTC),
                loss_description="Test",
                loss_cause=LossCause.OTHER,
                loss_location=valid_address,
                line_of_business=LineOfBusiness.OTHER,
                policy_number="P1",
                policy_effective_date=datetime(2025, 1, 1, tzinfo=UTC),
                policy_expiration_date=datetime(2024, 1, 1, tzinfo=UTC),
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                updated_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_system="test",
            )

    def test_claim_negative_total_paid_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["total_paid"] = Decimal("-1")
        with pytest.raises(ValidationError):
            Claim.model_validate(data)

    def test_claim_negative_total_reserved_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["total_reserved"] = Decimal("-1")
        with pytest.raises(ValidationError):
            Claim.model_validate(data)

    def test_claim_negative_total_incurred_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["total_incurred"] = Decimal("-1")
        with pytest.raises(ValidationError):
            Claim.model_validate(data)

    def test_claim_negative_deductible_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["deductible"] = Decimal("-1")
        with pytest.raises(ValidationError):
            Claim.model_validate(data)

    def test_claim_naive_loss_date_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["loss_date"] = datetime(2024, 3, 1)
        with pytest.raises(ValidationError):
            Claim.model_validate(data)

    def test_claim_with_exposures_succeeds(self, valid_claim: Claim) -> None:
        assert len(valid_claim.exposures) >= 2

    def test_claim_raw_data_accepts_dict(self, valid_claim: Claim) -> None:
        assert valid_claim.raw_data == {"source": "fixture"}

    def test_claim_exposure_claim_id_mismatch_raises_validation_error(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["exposures"][0]["claim_id"] = "WRONG"
        with pytest.raises(ValidationError):
            Claim.model_validate(data)


class TestExposure:
    """Exposure model tests."""

    def test_exposure_valid_succeeds(self, valid_claim: Claim) -> None:
        assert valid_claim.exposures[0].exposure_id == "EXP-1"

    def test_exposure_negative_reserved_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Exposure(
                exposure_id="E1",
                claim_id="C1",
                exposure_type=ExposureType.OTHER,
                coverage_type="X",
                reserved_amount=Decimal("-1"),
                claimant_id="CLMT",
            )

    def test_exposure_negative_paid_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Exposure(
                exposure_id="E1",
                claim_id="C1",
                exposure_type=ExposureType.OTHER,
                coverage_type="X",
                paid_amount=Decimal("-1"),
                claimant_id="CLMT",
            )

    def test_exposure_negative_deductible_amount_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Exposure(
                exposure_id="E1",
                claim_id="C1",
                exposure_type=ExposureType.OTHER,
                coverage_type="X",
                deductible_amount=Decimal("-1"),
                claimant_id="CLMT",
            )


class TestClaimant:
    """Claimant model tests."""

    def test_claimant_person_succeeds(self, valid_claim: Claim) -> None:
        assert valid_claim.claimants[0].first_name == "John"

    def test_claimant_organization_succeeds(self) -> None:
        c = Claimant(
            claimant_id="C1",
            claim_id="CLM",
            role=ContactRole.VENDOR,
            first_name="Acme",
            last_name="Corp",
            organization_name="Acme Corp",
        )
        assert c.organization_name == "Acme Corp"

    def test_claimant_missing_first_name_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Claimant(
                claimant_id="C1",
                claim_id="CLM",
                role=ContactRole.CLAIMANT,
                last_name="Doe",
            )

    def test_claimant_missing_last_name_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Claimant(
                claimant_id="C1",
                claim_id="CLM",
                role=ContactRole.CLAIMANT,
                first_name="Jane",
            )


class TestTransaction:
    """Transaction model tests."""

    def test_transaction_payment_succeeds(self, valid_claim: Claim) -> None:
        assert valid_claim.transactions[0].transaction_type == TransactionType.PAYMENT

    def test_transaction_recovery_succeeds(self, valid_claim: Claim) -> None:
        assert valid_claim.transactions[2].transaction_type == TransactionType.RECOVERY

    def test_transaction_currency_lowercase_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Transaction(
                transaction_id="T1",
                claim_id="C1",
                transaction_type=TransactionType.PAYMENT,
                amount=Decimal("100"),
                currency="usd",
                transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_transaction_currency_two_chars_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Transaction(
                transaction_id="T1",
                claim_id="C1",
                transaction_type=TransactionType.PAYMENT,
                amount=Decimal("100"),
                currency="US",
                transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_transaction_reserve_set_negative_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Transaction(
                transaction_id="T1",
                claim_id="C1",
                transaction_type=TransactionType.RESERVE_SET,
                amount=Decimal("-100"),
                transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_transaction_reserve_change_negative_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Transaction(
                transaction_id="T1",
                claim_id="C1",
                transaction_type=TransactionType.RESERVE_CHANGE,
                amount=Decimal("-50"),
                transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_transaction_payment_negative_amount_allowed(self) -> None:
        txn = Transaction(
            transaction_id="T1",
            claim_id="C1",
            transaction_type=TransactionType.PAYMENT,
            amount=Decimal("-100"),
            transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert txn.amount == Decimal("-100")


class TestPolicySnapshot:
    """PolicySnapshot model tests."""

    def test_policy_valid_succeeds(self, valid_policy: PolicySnapshot) -> None:
        assert valid_policy.policy_number == "POL-100"

    def test_policy_expiration_before_effective_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            PolicySnapshot(
                policy_number="P1",
                carrier_name="C",
                product_type="Auto",
                effective_date=datetime(2025, 1, 1, tzinfo=UTC),
                expiration_date=datetime(2024, 1, 1, tzinfo=UTC),
                insured_name="Jane",
            )

    def test_policy_negative_premium_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            PolicySnapshot(
                policy_number="P1",
                carrier_name="C",
                product_type="Auto",
                effective_date=datetime(2024, 1, 1, tzinfo=UTC),
                expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
                insured_name="Jane",
                premium=Decimal("-1"),
            )

    def test_policy_with_coverages_succeeds(self, valid_policy: PolicySnapshot) -> None:
        assert len(valid_policy.coverages) == 1

    def test_policy_snapshot_naive_effective_date_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            PolicySnapshot(
                policy_number="P1",
                carrier_name="C",
                product_type="Auto",
                effective_date=datetime(2024, 1, 1),
                expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
                insured_name="Jane",
            )


class TestJsonRoundTrip:
    """JSON serialization round-trip for all models."""

    def test_address_json_roundtrip(self, valid_address: Address) -> None:
        restored = Address.model_validate_json(valid_address.model_dump_json())
        assert restored == valid_address

    def test_coverage_json_roundtrip(self) -> None:
        cov = Coverage(
            coverage_type="GL",
            limit=Decimal("1000000"),
            deductible=Decimal("0"),
            premium=Decimal("5000"),
        )
        restored = Coverage.model_validate_json(cov.model_dump_json())
        assert restored == cov

    def test_policy_snapshot_json_roundtrip(self, valid_policy: PolicySnapshot) -> None:
        restored = PolicySnapshot.model_validate_json(valid_policy.model_dump_json())
        assert restored == valid_policy

    def test_exposure_json_roundtrip(self, valid_claim: Claim) -> None:
        exp = valid_claim.exposures[0]
        restored = Exposure.model_validate_json(exp.model_dump_json())
        assert restored == exp

    def test_claimant_json_roundtrip(self, valid_claim: Claim) -> None:
        clm = valid_claim.claimants[0]
        restored = Claimant.model_validate_json(clm.model_dump_json())
        assert restored == clm

    def test_transaction_json_roundtrip(self, valid_claim: Claim) -> None:
        txn = valid_claim.transactions[0]
        restored = Transaction.model_validate_json(txn.model_dump_json())
        assert restored == txn

    def test_claim_json_roundtrip(self, valid_claim: Claim) -> None:
        restored = Claim.model_validate_json(valid_claim.model_dump_json())
        assert restored == valid_claim

    def test_valid_claim_fixture_counts(self, valid_claim: Claim) -> None:
        assert len(valid_claim.exposures) >= 2
        assert len(valid_claim.claimants) >= 2
        assert len(valid_claim.transactions) >= 3


class TestPackageImports:
    """Smoke test for public package exports."""

    def test_schema_imports_succeed(self) -> None:
        from src.exceptions import AdaptInsureError, SchemaValidationError
        from src.schema import (
            BaseAdapter,
            TransformResult,
            validate_claim_consistency,
        )

        assert AdaptInsureError is not None
        assert SchemaValidationError is not None
        assert BaseAdapter is not None
        assert TransformResult is not None
        assert validate_claim_consistency is not None
