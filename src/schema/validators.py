"""Reusable validation helpers for schema models and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schema.models import Claim

from src.schema.enums import ClaimStatus, ContactRole


@dataclass(frozen=True)
class ValidationWarning:
    """Non-fatal validation issue on a claim record."""

    field_name: str
    message: str
    severity: str = "warning"


def validate_date_order(
    earlier: datetime,
    later: datetime,
    earlier_name: str,
    later_name: str,
) -> None:
    """Raise ValueError if later is strictly before earlier."""
    if later < earlier:
        msg = f"{later_name} must be on or after {earlier_name}"
        raise ValueError(msg)


def validate_non_negative(value: Decimal, field_name: str) -> None:
    """Raise ValueError if a monetary amount is negative."""
    if value < 0:
        msg = f"{field_name} must be greater than or equal to zero"
        raise ValueError(msg)


def validate_currency_code(code: str) -> None:
    """Raise ValueError if code is not a 3-letter uppercase ISO 4217 code."""
    if len(code) != 3 or not code.isascii() or not code.isupper():
        msg = "currency must be exactly 3 uppercase ASCII letters (ISO 4217)"
        raise ValueError(msg)


def validate_timezone_aware(dt: datetime, field_name: str) -> None:
    """Raise ValueError if datetime is naive (no tzinfo)."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


def validate_claim_consistency(claim: Claim) -> list[ValidationWarning]:
    """Return warnings for cross-field inconsistencies (does not raise)."""
    warnings: list[ValidationWarning] = []

    expected_incurred = claim.total_paid + claim.total_reserved
    if claim.total_incurred != expected_incurred:
        warnings.append(
            ValidationWarning(
                field_name="total_incurred",
                message=(
                    f"total_incurred ({claim.total_incurred}) does not equal "
                    f"total_paid + total_reserved ({expected_incurred})"
                ),
            )
        )

    if claim.status == ClaimStatus.CLOSED and claim.closed_date is None:
        warnings.append(
            ValidationWarning(
                field_name="closed_date",
                message="closed_date should be present when status is closed",
            )
        )

    if claim.litigation_flag:
        has_attorney = any(c.role == ContactRole.ATTORNEY for c in claim.claimants)
        if not has_attorney:
            warnings.append(
                ValidationWarning(
                    field_name="litigation_flag",
                    message="litigation_flag is true but no claimant has role attorney",
                )
            )

    return warnings
