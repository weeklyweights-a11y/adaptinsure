"""Tests for schema validator functions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.schema import (
    Claim,
    ClaimStatus,
    ContactRole,
    validate_claim_consistency,
    validate_currency_code,
    validate_date_order,
    validate_non_negative,
    validate_timezone_aware,
)
from tests.conftest import UTC


class TestValidateDateOrder:
    """validate_date_order tests."""

    def test_validate_date_order_valid_passes(self) -> None:
        earlier = datetime(2024, 1, 1, tzinfo=UTC)
        later = datetime(2024, 1, 2, tzinfo=UTC)
        validate_date_order(earlier, later, "earlier", "later")

    def test_validate_date_order_reversed_raises_value_error(self) -> None:
        earlier = datetime(2024, 1, 5, tzinfo=UTC)
        later = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="must be on or after"):
            validate_date_order(earlier, later, "earlier", "later")

    def test_validate_date_order_equal_dates_passes(self) -> None:
        same = datetime(2024, 1, 1, tzinfo=UTC)
        validate_date_order(same, same, "a", "b")


class TestValidateNonNegative:
    """validate_non_negative tests."""

    def test_validate_non_negative_zero_passes(self) -> None:
        validate_non_negative(Decimal("0"), "amount")

    def test_validate_non_negative_positive_passes(self) -> None:
        validate_non_negative(Decimal("10.5"), "amount")

    def test_validate_non_negative_negative_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must be greater than or equal"):
            validate_non_negative(Decimal("-0.01"), "amount")


class TestValidateCurrencyCode:
    """validate_currency_code tests."""

    def test_validate_currency_code_usd_passes(self) -> None:
        validate_currency_code("USD")

    def test_validate_currency_code_eur_passes(self) -> None:
        validate_currency_code("EUR")

    def test_validate_currency_code_lowercase_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            validate_currency_code("usd")

    def test_validate_currency_code_two_chars_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            validate_currency_code("US")

    def test_validate_currency_code_four_chars_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            validate_currency_code("USDD")


class TestValidateTimezoneAware:
    """validate_timezone_aware tests."""

    def test_validate_timezone_aware_aware_passes(self) -> None:
        validate_timezone_aware(datetime(2024, 1, 1, tzinfo=UTC), "dt")

    def test_validate_timezone_aware_naive_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            validate_timezone_aware(datetime(2024, 1, 1), "dt")


class TestValidateClaimConsistency:
    """validate_claim_consistency tests."""

    def test_validate_claim_consistency_consistent_returns_empty(
        self,
        valid_claim: Claim,
    ) -> None:
        assert validate_claim_consistency(valid_claim) == []

    def test_validate_claim_consistency_incurred_mismatch_returns_warning(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["total_incurred"] = Decimal("99999")
        claim = Claim.model_validate(data)
        warnings = validate_claim_consistency(claim)
        assert any(w.field_name == "total_incurred" for w in warnings)

    def test_validate_claim_consistency_closed_without_date_returns_warning(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["status"] = ClaimStatus.CLOSED
        data["closed_date"] = None
        claim = Claim.model_validate(data)
        warnings = validate_claim_consistency(claim)
        assert any(w.field_name == "closed_date" for w in warnings)

    def test_validate_claim_consistency_litigation_without_attorney_returns_warning(
        self,
        valid_claim: Claim,
    ) -> None:
        data = valid_claim.model_dump()
        data["litigation_flag"] = True
        claim = Claim.model_validate(data)
        warnings = validate_claim_consistency(claim)
        assert any(w.field_name == "litigation_flag" for w in warnings)
