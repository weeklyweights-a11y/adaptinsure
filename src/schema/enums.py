"""Insurance domain enumerations for the universal claims schema."""

from __future__ import annotations

from enum import StrEnum


class ClaimStatus(StrEnum):
    """Lifecycle state of a claim."""

    OPEN = "open"
    CLOSED = "closed"
    REOPENED = "reopened"
    DENIED = "denied"
    PENDING = "pending"


class ExposureStatus(StrEnum):
    """State of an exposure within a claim."""

    OPEN = "open"
    CLOSED = "closed"


class ExposureType(StrEnum):
    """Kind of loss an exposure covers."""

    VEHICLE_DAMAGE = "vehicle_damage"
    BODILY_INJURY = "bodily_injury"
    PROPERTY_DAMAGE = "property_damage"
    MED_PAY = "med_pay"
    PIP = "pip"
    UM_UIM = "um_uim"
    LIABILITY = "liability"
    CARGO = "cargo"
    OTHER = "other"


class ContactRole(StrEnum):
    """Role a person or organization plays on a claim."""

    INSURED = "insured"
    CLAIMANT = "claimant"
    WITNESS = "witness"
    ATTORNEY = "attorney"
    ADJUSTER = "adjuster"
    VENDOR = "vendor"
    OTHER = "other"


class TransactionType(StrEnum):
    """Kind of financial movement."""

    PAYMENT = "payment"
    RECOVERY = "recovery"
    RESERVE_SET = "reserve_set"
    RESERVE_CHANGE = "reserve_change"


class TransactionStatus(StrEnum):
    """Lifecycle state of a transaction."""

    PENDING = "pending"
    APPROVED = "approved"
    POSTED = "posted"
    VOIDED = "voided"


class LineOfBusiness(StrEnum):
    """Insurance product line."""

    PERSONAL_AUTO = "personal_auto"
    COMMERCIAL_AUTO = "commercial_auto"
    HOMEOWNERS = "homeowners"
    COMMERCIAL_PROPERTY = "commercial_property"
    GENERAL_LIABILITY = "general_liability"
    WORKERS_COMP = "workers_comp"
    PROFESSIONAL_LIABILITY = "professional_liability"
    UMBRELLA = "umbrella"
    INLAND_MARINE = "inland_marine"
    OTHER = "other"


class LossCause(StrEnum):
    """Cause of the loss."""

    COLLISION = "collision"
    THEFT = "theft"
    FIRE = "fire"
    WEATHER = "weather"
    WATER_DAMAGE = "water_damage"
    VANDALISM = "vandalism"
    SLIP_AND_FALL = "slip_and_fall"
    PRODUCT_LIABILITY = "product_liability"
    MEDICAL_MALPRACTICE = "medical_malpractice"
    WORKPLACE_INJURY = "workplace_injury"
    OTHER = "other"
