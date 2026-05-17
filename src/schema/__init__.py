"""Universal insurance claims schema — public exports."""

from src.schema.base_adapter import BaseAdapter, TransformResult
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
from src.schema.validators import (
    ValidationWarning,
    validate_claim_consistency,
    validate_currency_code,
    validate_date_order,
    validate_non_negative,
    validate_timezone_aware,
)

__all__ = [
    "Address",
    "BaseAdapter",
    "Claim",
    "Claimant",
    "ClaimStatus",
    "ContactRole",
    "Coverage",
    "Exposure",
    "ExposureStatus",
    "ExposureType",
    "LineOfBusiness",
    "LossCause",
    "PolicySnapshot",
    "Transaction",
    "TransactionStatus",
    "TransactionType",
    "TransformResult",
    "ValidationWarning",
    "validate_claim_consistency",
    "validate_currency_code",
    "validate_date_order",
    "validate_non_negative",
    "validate_timezone_aware",
]
