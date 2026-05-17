"""Pydantic models for the universal insurance claims schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
from src.schema.validators import (
    validate_currency_code,
    validate_date_order,
    validate_non_negative,
    validate_timezone_aware,
)


class Address(BaseModel):
    """Postal address."""

    model_config = ConfigDict(strict=True, frozen=True)

    street_1: Annotated[str, Field(description="Primary street address")]
    street_2: Annotated[str | None, Field(default=None, description="Apartment, suite, or unit")]
    city: Annotated[str, Field(description="City name")]
    state: Annotated[str, Field(description="State or region code")]
    postal_code: Annotated[str, Field(description="Postal or ZIP code as string")]
    country: Annotated[str, Field(default="US", description="ISO 3166-1 alpha-2 country code")]


class Coverage(BaseModel):
    """Coverage line on a policy."""

    model_config = ConfigDict(strict=True, frozen=True)

    coverage_type: Annotated[str, Field(description="Coverage name")]
    limit: Annotated[Decimal, Field(description="Coverage limit amount")]
    deductible: Annotated[Decimal, Field(description="Deductible for this coverage")]
    premium: Annotated[Decimal, Field(description="Premium for this coverage")]

    @field_validator("limit", "deductible", "premium")
    @classmethod
    def check_non_negative_amounts(cls, value: Decimal, info: Any) -> Decimal:
        """Ensure monetary fields are not negative."""
        validate_non_negative(value, str(info.field_name))
        return value


class Exposure(BaseModel):
    """Coverage-level line item within a claim."""

    model_config = ConfigDict(strict=True)

    exposure_id: Annotated[str, Field(description="Exposure identifier")]
    claim_id: Annotated[str, Field(description="Parent claim identifier")]
    exposure_type: Annotated[ExposureType, Field(description="Type of loss")]
    coverage_type: Annotated[str, Field(description="Coverage type label")]
    status: Annotated[ExposureStatus, Field(default=ExposureStatus.OPEN)]
    reserved_amount: Annotated[Decimal, Field(default=Decimal("0"))]
    paid_amount: Annotated[Decimal, Field(default=Decimal("0"))]
    deductible_amount: Annotated[Decimal, Field(default=Decimal("0"))]
    claimant_id: Annotated[str, Field(description="Claimant linked to this exposure")]

    @field_validator("reserved_amount", "paid_amount", "deductible_amount")
    @classmethod
    def check_non_negative_amounts(cls, value: Decimal, info: Any) -> Decimal:
        """Ensure monetary fields are not negative."""
        validate_non_negative(value, str(info.field_name))
        return value


class Claimant(BaseModel):
    """Person or organization on a claim."""

    model_config = ConfigDict(strict=True)

    claimant_id: Annotated[str, Field(description="Claimant identifier")]
    claim_id: Annotated[str, Field(description="Parent claim identifier")]
    role: Annotated[ContactRole, Field(description="Role on the claim")]
    first_name: Annotated[str, Field(description="Given name")]
    last_name: Annotated[str, Field(description="Family name")]
    organization_name: Annotated[str | None, Field(default=None)]
    email: Annotated[str | None, Field(default=None)]
    phone: Annotated[str | None, Field(default=None)]
    address: Annotated[Address | None, Field(default=None)]
    date_of_birth: Annotated[date | None, Field(default=None)]


class Transaction(BaseModel):
    """Financial movement on a claim."""

    model_config = ConfigDict(strict=True)

    transaction_id: Annotated[str, Field(description="Transaction identifier")]
    claim_id: Annotated[str, Field(description="Parent claim identifier")]
    exposure_id: Annotated[str | None, Field(default=None)]
    transaction_type: Annotated[TransactionType, Field(description="Transaction kind")]
    amount: Annotated[Decimal, Field(description="Transaction amount")]
    currency: Annotated[str, Field(default="USD", description="ISO 4217 currency code")]
    transaction_date: Annotated[datetime, Field(description="When the transaction occurred")]
    check_number: Annotated[str | None, Field(default=None)]
    payee_name: Annotated[str | None, Field(default=None)]
    status: Annotated[TransactionStatus, Field(default=TransactionStatus.PENDING)]

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str) -> str:
        """Validate ISO 4217 currency code format."""
        validate_currency_code(value)
        return value

    @field_validator("transaction_date")
    @classmethod
    def check_transaction_date_tz(cls, value: datetime) -> datetime:
        """Require timezone-aware transaction datetime."""
        validate_timezone_aware(value, "transaction_date")
        return value

    @model_validator(mode="after")
    def check_reserve_amounts(self) -> Transaction:
        """Reserve transactions must not have negative amounts."""
        if self.transaction_type in (
            TransactionType.RESERVE_SET,
            TransactionType.RESERVE_CHANGE,
        ):
            validate_non_negative(self.amount, "amount")
        return self


class PolicySnapshot(BaseModel):
    """Policy data at time of loss."""

    model_config = ConfigDict(strict=True)

    policy_number: Annotated[str, Field(description="Policy number")]
    carrier_name: Annotated[str, Field(description="Carrier name")]
    product_type: Annotated[str, Field(description="Product type")]
    effective_date: Annotated[datetime, Field(description="Policy effective date")]
    expiration_date: Annotated[datetime, Field(description="Policy expiration date")]
    insured_name: Annotated[str, Field(description="Named insured")]
    coverages: Annotated[list[Coverage], Field(default_factory=list)]
    premium: Annotated[Decimal, Field(default=Decimal("0"))]

    @field_validator("effective_date", "expiration_date")
    @classmethod
    def check_policy_dates_tz(cls, value: datetime, info: Any) -> datetime:
        """Require timezone-aware policy datetimes."""
        validate_timezone_aware(value, str(info.field_name))
        return value

    @field_validator("premium")
    @classmethod
    def check_premium(cls, value: Decimal) -> Decimal:
        """Ensure premium is not negative."""
        validate_non_negative(value, "premium")
        return value

    @model_validator(mode="after")
    def check_expiration_after_effective(self) -> PolicySnapshot:
        """Expiration must be after effective date."""
        validate_date_order(
            self.effective_date,
            self.expiration_date,
            "effective_date",
            "expiration_date",
        )
        if self.expiration_date <= self.effective_date:
            msg = "expiration_date must be after effective_date"
            raise ValueError(msg)
        return self


class Claim(BaseModel):
    """Central insurance claim record."""

    model_config = ConfigDict(strict=True)

    claim_id: Annotated[str, Field(description="Unique claim identifier")]
    claim_number: Annotated[str, Field(description="Human-readable claim number")]
    status: Annotated[ClaimStatus, Field(description="Claim lifecycle status")]
    loss_date: Annotated[datetime, Field(description="When the loss occurred")]
    reported_date: Annotated[datetime, Field(description="When the claim was reported (FNOL)")]
    closed_date: Annotated[datetime | None, Field(default=None)]
    loss_description: Annotated[str, Field(description="Description of the loss")]
    loss_cause: Annotated[LossCause, Field(description="Cause of loss")]
    loss_location: Annotated[Address, Field(description="Location of loss")]
    line_of_business: Annotated[LineOfBusiness, Field(description="Product line")]
    policy_number: Annotated[str, Field(description="Policy number")]
    policy_effective_date: Annotated[datetime, Field(description="Policy effective date")]
    policy_expiration_date: Annotated[datetime, Field(description="Policy expiration date")]
    total_incurred: Annotated[Decimal, Field(default=Decimal("0"))]
    total_paid: Annotated[Decimal, Field(default=Decimal("0"))]
    total_reserved: Annotated[Decimal, Field(default=Decimal("0"))]
    deductible: Annotated[Decimal, Field(default=Decimal("0"))]
    catastrophe_code: Annotated[str | None, Field(default=None)]
    litigation_flag: Annotated[bool, Field(default=False)]
    subrogation_flag: Annotated[bool, Field(default=False)]
    fraud_flag: Annotated[bool, Field(default=False)]
    adjuster_id: Annotated[str | None, Field(default=None)]
    adjuster_name: Annotated[str | None, Field(default=None)]
    created_at: Annotated[datetime, Field(description="Record creation timestamp")]
    updated_at: Annotated[datetime, Field(description="Record update timestamp")]
    source_system: Annotated[str, Field(description="Source CMS or carrier identifier")]
    raw_data: Annotated[dict[str, Any], Field(default_factory=dict, description="Original record")]
    exposures: Annotated[list[Exposure], Field(default_factory=list)]
    claimants: Annotated[list[Claimant], Field(default_factory=list)]
    transactions: Annotated[list[Transaction], Field(default_factory=list)]

    @field_validator(
        "loss_date",
        "reported_date",
        "closed_date",
        "policy_effective_date",
        "policy_expiration_date",
        "created_at",
        "updated_at",
    )
    @classmethod
    def check_datetimes_tz(cls, value: datetime | None, info: Any) -> datetime | None:
        """Require timezone-aware datetimes when present."""
        if value is None:
            return value
        validate_timezone_aware(value, str(info.field_name))
        return value

    @field_validator("total_incurred", "total_paid", "total_reserved", "deductible")
    @classmethod
    def check_non_negative_totals(cls, value: Decimal, info: Any) -> Decimal:
        """Ensure claim-level monetary fields are not negative."""
        validate_non_negative(value, str(info.field_name))
        return value

    @model_validator(mode="after")
    def check_dates_and_children(self) -> Claim:
        """Validate date ordering and nested entity consistency."""
        validate_date_order(self.loss_date, self.reported_date, "loss_date", "reported_date")

        if self.closed_date is not None:
            validate_date_order(
                self.reported_date,
                self.closed_date,
                "reported_date",
                "closed_date",
            )

        validate_date_order(
            self.policy_effective_date,
            self.policy_expiration_date,
            "policy_effective_date",
            "policy_expiration_date",
        )
        if self.policy_expiration_date <= self.policy_effective_date:
            msg = "policy_expiration_date must be after policy_effective_date"
            raise ValueError(msg)

        for exposure in self.exposures:
            if exposure.claim_id != self.claim_id:
                msg = (
                    f"exposure {exposure.exposure_id} claim_id "
                    f"({exposure.claim_id}) must match claim claim_id ({self.claim_id})"
                )
                raise ValueError(msg)

        return self


Claim.model_rebuild()
PolicySnapshot.model_rebuild()
Transaction.model_rebuild()
Claimant.model_rebuild()
Exposure.model_rebuild()
