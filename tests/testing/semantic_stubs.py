"""Per-insurer semantic matcher stubs for full pipeline tests."""

from __future__ import annotations

from src.discovery.profile import FieldInfo
from src.mapping.config import FieldMapping, FieldTransform, MatchType, TransformType
from src.mapping.semantic_matcher import SemanticMatchOutcome, SemanticMatcher

ISO_DATE = FieldTransform(
    transform_type=TransformType.DATE_FORMAT,
    source_format="YYYY-MM-DD",
    target_format="ISO 8601",
)
ISO_DT = ISO_DATE
MMDDYYYY = FieldTransform(
    transform_type=TransformType.DATE_FORMAT,
    source_format="MM/DD/YYYY",
    target_format="ISO 8601",
)
YYYYMMDD = FieldTransform(
    transform_type=TransformType.DATE_FORMAT,
    source_format="YYYYMMDD",
    target_format="ISO 8601",
)
CURRENCY = FieldTransform(
    transform_type=TransformType.CURRENCY_PARSE,
    source_format="$#,###.##",
    target_format="Decimal",
)
BOOLEAN_YN = FieldTransform(
    transform_type=TransformType.BOOLEAN_PARSE,
    parameters={
        "true_values": ["Y", "y", "true", "1"],
        "false_values": ["N", "n", "false", "0"],
    },
)

GW_TARGETS: dict[str, tuple[str, float, FieldTransform | None]] = {
    "claimId": ("claim.claim_id", 0.95, None),
    "claimNumber": ("claim.claim_number", 0.95, None),
    "lossDate": ("claim.loss_date", 0.9, ISO_DT),
    "reportedDate": ("claim.reported_date", 0.9, ISO_DT),
    "closedDate": ("claim.closed_date", 0.85, ISO_DT),
    "claimState": (
        "claim.status",
        0.85,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "ClaimStatus",
                "enum_map": {
                    "open": "open",
                    "closed": "closed",
                    "denied": "denied",
                    "reopened": "reopened",
                    "pending": "pending",
                },
                "target_field": "claim.status",
            },
        ),
    ),
    "lossCause": (
        "claim.loss_cause",
        0.85,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "LossCause",
                "enum_map": {
                    "collision": "collision",
                    "CT:collision": "collision",
                    "CT:theft": "theft",
                    "theft": "theft",
                    "fire": "fire",
                    "water_damage": "water_damage",
                    "weather": "weather",
                    "slip_and_fall": "slip_and_fall",
                    "product_liability": "product_liability",
                    "workplace_injury": "workplace_injury",
                },
                "target_field": "claim.loss_cause",
            },
        ),
    ),
    "lossDescription": ("claim.loss_description", 0.88, None),
    "lineOfBusiness": (
        "claim.line_of_business",
        0.85,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "LineOfBusiness",
                "enum_map": {
                    "personal_auto": "personal_auto",
                    "homeowners": "homeowners",
                    "general_liability": "general_liability",
                    "workers_comp": "workers_comp",
                },
                "target_field": "claim.line_of_business",
            },
        ),
    ),
    "policyNumber": ("claim.policy_number", 0.9, None),
    "policyEffDate": ("claim.policy_effective_date", 0.9, ISO_DT),
    "policyExpDate": ("claim.policy_expiration_date", 0.9, ISO_DT),
    "totalIncurred": ("claim.total_incurred", 0.9, CURRENCY),
    "totalPaid": ("claim.total_paid", 0.9, CURRENCY),
    "totalReserves": ("claim.total_reserved", 0.9, CURRENCY),
    "deductible": ("claim.deductible", 0.88, CURRENCY),
    "catastropheCode": ("claim.catastrophe_code", 0.8, None),
    "fraudIndicator": ("claim.fraud_flag", 0.8, BOOLEAN_YN),
    "assignedAdjusterId": ("claim.adjuster_id", 0.8, None),
    "assignedAdjusterName": ("claim.adjuster_name", 0.8, None),
    "street": ("claim.loss_location.street_1", 0.75, None),
    "city": ("claim.loss_location.city", 0.75, None),
    "state": ("claim.loss_location.state", 0.75, None),
    "postalCode": ("claim.loss_location.postal_code", 0.75, None),
}

ACORD_TARGETS: dict[str, tuple[str, float, FieldTransform | None]] = {
    "ClaimNumber": ("claim.claim_id", 0.95, None),
    "LossDt": ("claim.loss_date", 0.9, ISO_DATE),
    "ReportedDt": ("claim.reported_date", 0.9, ISO_DATE),
    "ClaimStatusCd": (
        "claim.status",
        0.85,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "ClaimStatus",
                "enum_map": {"open": "open", "closed": "closed"},
                "target_field": "claim.status",
            },
        ),
    ),
    "LOBCd": (
        "claim.line_of_business",
        0.8,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "LineOfBusiness",
                "enum_map": {"PA": "personal_auto", "HO": "homeowners", "GL": "general_liability"},
                "target_field": "claim.line_of_business",
            },
        ),
    ),
    "LossDesc": ("claim.loss_description", 0.88, None),
    "CatastropheCd": ("claim.catastrophe_code", 0.8, None),
    "PolicyNumber": ("claim.policy_number", 0.9, None),
    "EffectiveDt": ("claim.policy_effective_date", 0.9, ISO_DATE),
    "ExpirationDt": ("claim.policy_expiration_date", 0.9, ISO_DATE),
    "PaymentAmt": ("claim.total_paid", 0.85, CURRENCY),
    "CheckNumber": ("claim.claim_number", 0.5, None),
    "PayeeName": ("claim.adjuster_name", 0.5, None),
    "Addr1": ("claim.loss_location.street_1", 0.75, None),
    "City": ("claim.loss_location.city", 0.75, None),
    "StateProvCd": ("claim.loss_location.state", 0.75, None),
    "PostalCode": ("claim.loss_location.postal_code", 0.75, None),
    "InternalRefNum": ("claim.claim_id", 0.7, None),
}

LEGACY_TARGETS: dict[str, tuple[str, float, FieldTransform | None]] = {
    "CLM_NBR": ("claim.claim_id", 0.95, None),
    "DT_OF_LSS": ("claim.loss_date", 0.9, YYYYMMDD),
    "RPTD_DT": ("claim.reported_date", 0.9, YYYYMMDD),
    "CLS_DT": ("claim.closed_date", 0.85, YYYYMMDD),
    "CLM_STS": (
        "claim.status",
        0.85,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "ClaimStatus",
                "enum_map": {
                    "O": "open",
                    "C": "closed",
                    "D": "denied",
                    "R": "reopened",
                    "P": "pending",
                },
                "target_field": "claim.status",
            },
        ),
    ),
    "LSS_DESC": ("claim.loss_description", 0.88, None),
    "LSS_CAUSE": (
        "claim.loss_cause",
        0.8,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "LossCause",
                "enum_map": {
                    "COLL": "collision",
                    "FIRE": "fire",
                    "THEFT": "theft",
                    "WATER": "water_damage",
                },
                "target_field": "claim.loss_cause",
            },
        ),
    ),
    "LOB": (
        "claim.line_of_business",
        0.8,
        FieldTransform(
            transform_type=TransformType.ENUM_MAP,
            parameters={
                "enum_name": "LineOfBusiness",
                "enum_map": {"PA": "personal_auto", "HO": "homeowners", "GL": "general_liability"},
                "target_field": "claim.line_of_business",
            },
        ),
    ),
    "POL_NBR": ("claim.policy_number", 0.9, None),
    "POL_EFF": ("claim.policy_effective_date", 0.9, YYYYMMDD),
    "POL_EXP": ("claim.policy_expiration_date", 0.9, YYYYMMDD),
    "TOT_INCR": ("claim.total_incurred", 0.9, CURRENCY),
    "TOT_PD": ("claim.total_paid", 0.9, CURRENCY),
    "TOT_RSV": ("claim.total_reserved", 0.9, CURRENCY),
    "DED_AMT": ("claim.deductible", 0.88, CURRENCY),
    "CAT_CD": ("claim.catastrophe_code", 0.8, None),
    "LIT_FLG": ("claim.litigation_flag", 0.8, BOOLEAN_YN),
    "SUBR_FLG": ("claim.subrogation_flag", 0.8, BOOLEAN_YN),
    "FRD_FLG": ("claim.fraud_flag", 0.8, BOOLEAN_YN),
    "ADJ_ID": ("claim.adjuster_id", 0.8, None),
    "ADJ_NM": ("claim.adjuster_name", 0.8, None),
    "LSS_ST1": ("claim.loss_location.street_1", 0.75, None),
    "LSS_CITY": ("claim.loss_location.city", 0.75, None),
    "LSS_ST": ("claim.loss_location.state", 0.75, None),
    "LSS_ZIP": ("claim.loss_location.postal_code", 0.75, None),
    "SRC_SYS": ("claim.source_system", 0.9, None),
}


class _InsurerSemanticStub(SemanticMatcher):
    """Maps discovered fields using a static target table (Strategy A: claim-level)."""

    def __init__(self, targets: dict[str, tuple[str, float, FieldTransform | None]]) -> None:
        self._targets = targets

    async def match(self, unmatched_fields, already_mapped_targets, **kwargs):  # type: ignore[no-untyped-def]
        del already_mapped_targets, kwargs
        mappings: list[FieldMapping] = []
        for field in unmatched_fields:
            if self._skip_field(field):
                continue
            entry = self._resolve(field)
            if entry is None:
                continue
            target, confidence, transform = entry
            if not target.startswith("claim."):
                continue
            mappings.append(
                FieldMapping(
                    source_field=field.source_name,
                    source_path=field.nesting_path,
                    target_field=target,
                    match_type=MatchType.SEMANTIC,
                    confidence=confidence,
                    reasoning="pipeline semantic stub",
                    transform=transform,
                ),
            )
        return SemanticMatchOutcome(mappings=mappings, gaps=[])

    @staticmethod
    def _skip_field(field: FieldInfo) -> bool:
        path = field.nesting_path or ""
        skip_segments = ("exposures", "contacts", "transactions", "ClaimsParty", "Coverage")
        if any(seg in path for seg in skip_segments):
            return True
        if field.source_name in (
            "exposureId",
            "contactId",
            "transactionId",
            "claimantId",
            "amount",
            "currency",
        ):
            return True
        address_leafs = ("street", "city", "state", "postalCode", "Addr1", "City")
        if field.source_name in address_leafs and "lossLocation" not in path and "LossLocation" not in path:
            if "lossLocationAddress" not in path and "Address" not in path:
                return True
        return False

    def _resolve(
        self,
        field: FieldInfo,
    ) -> tuple[str, float, FieldTransform | None] | None:
        if field.source_name in self._targets:
            return self._targets[field.source_name]
        path = field.nesting_path or ""
        leaf = path.split(".")[-1] if path else field.source_name
        if leaf in self._targets:
            return self._targets[leaf]
        return None


def guidewire_semantic_matcher() -> SemanticMatcher:
    return _InsurerSemanticStub(GW_TARGETS)


def acord_semantic_matcher() -> SemanticMatcher:
    return _InsurerSemanticStub(ACORD_TARGETS)


def legacy_semantic_matcher() -> SemanticMatcher:
    return _InsurerSemanticStub(LEGACY_TARGETS)
