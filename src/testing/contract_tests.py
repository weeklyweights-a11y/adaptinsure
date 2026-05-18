"""Contract test runner for generated adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schema.base_adapter import BaseAdapter
from src.schema.enums import ClaimStatus, LossCause
from src.schema.models import Claim


class ContractFailure(BaseModel):
    """Single contract check failure."""

    model_config = ConfigDict(strict=True)

    claim_id: str | None = None
    claim_number: str | None = None
    check_name: str
    expected: str
    actual: str
    severity: Literal["error", "warning"] = "error"


class ContractTestResult(BaseModel):
    """Aggregated contract test outcome."""

    model_config = ConfigDict(strict=True)

    total_claims: int = 0
    passed_claims: int = 0
    failed_claims: int = 0
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    failures: list[ContractFailure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pass_rate: float = 0.0


class ContractTestRunner:
    """Runs contract validation checks against adapter output."""

    _REQUIRED_FIELDS = (
        "claim_id",
        "claim_number",
        "status",
        "loss_date",
        "reported_date",
        "loss_description",
        "source_system",
    )

    def run(
        self,
        adapter: BaseAdapter,
        raw_input: str | bytes,
        expected_count: int | None = None,
    ) -> ContractTestResult:
        """Run transform_batch then per-claim checks."""
        result = adapter.transform_batch(raw_input)
        if expected_count is not None and result.total_records != expected_count:
            failure = ContractFailure(
                check_name="record_count",
                expected=str(expected_count),
                actual=str(result.total_records),
            )
            out = ContractTestResult(
                total_claims=result.total_records,
                failed_claims=result.total_records,
                total_checks=1,
                failed_checks=1,
                failures=[failure],
            )
            out.pass_rate = 0.0
            return out
        claims = [claim for claim, _warnings in result.successful]
        return self._run_on_claims(claims)

    def run_records(
        self,
        adapter: BaseAdapter,
        raw_records: list[dict[str, object]],
    ) -> ContractTestResult:
        """Map and validate each raw record without transform_batch."""
        claims: list[Claim] = []
        for raw in raw_records:
            try:
                mapped = adapter.map_record(raw)
                claim, _warnings = adapter.validate_record(mapped)
                claims.append(claim)
            except Exception:
                continue
        return self._run_on_claims(claims)

    def _run_on_claims(self, claims: list[Claim]) -> ContractTestResult:
        failures: list[ContractFailure] = []
        warnings: list[str] = []
        total_checks = 0
        passed_checks = 0
        passed_claims = 0

        for claim in claims:
            claim_failures, claim_warnings, claim_passed, claim_total = self._check_claim(claim)
            failures.extend(claim_failures)
            warnings.extend(claim_warnings)
            total_checks += claim_total
            passed_checks += claim_passed
            if not claim_failures:
                passed_claims += 1

        failed_claims = len(claims) - passed_claims
        failed_checks = total_checks - passed_checks
        pass_rate = passed_checks / total_checks if total_checks else 0.0
        return ContractTestResult(
            total_claims=len(claims),
            passed_claims=passed_claims,
            failed_claims=failed_claims,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            failures=failures,
            warnings=warnings,
            pass_rate=pass_rate,
        )

    def _check_claim(
        self,
        claim: Claim,
    ) -> tuple[list[ContractFailure], list[str], int, int]:
        failures: list[ContractFailure] = []
        warnings: list[str] = []
        passed = 0
        total = 0

        def record(
            check_name: str,
            ok: bool,
            *,
            expected: str = "",
            actual: str = "",
            severity: Literal["error", "warning"] = "error",
        ) -> None:
            nonlocal passed, total
            total += 1
            if ok:
                passed += 1
            else:
                failures.append(
                    ContractFailure(
                        claim_id=claim.claim_id,
                        claim_number=claim.claim_number,
                        check_name=check_name,
                        expected=expected,
                        actual=actual,
                        severity=severity,
                    )
                )

        record("schema_compliance:isinstance", isinstance(claim, Claim))

        for field_name in self._REQUIRED_FIELDS:
            value = getattr(claim, field_name, None)
            ok = value is not None and (value != "" if isinstance(value, str) else True)
            record(
                f"required_field:{field_name}",
                ok,
                expected="non-empty",
                actual=repr(value),
            )

        record(
            "type_correctness:loss_date_tz",
            claim.loss_date.tzinfo is not None,
            expected="timezone-aware",
            actual=str(claim.loss_date.tzinfo),
        )
        record(
            "type_correctness:total_paid_decimal",
            isinstance(claim.total_paid, Decimal),
            expected="Decimal",
            actual=type(claim.total_paid).__name__,
        )
        record(
            "type_correctness:status_enum",
            isinstance(claim.status, ClaimStatus),
            expected="ClaimStatus",
            actual=type(claim.status).__name__,
        )

        now = datetime.now(tz=UTC)
        record(
            "date_sanity:future_loss_date",
            claim.loss_date <= now,
            expected="<= now",
            actual=claim.loss_date.isoformat(),
        )
        record(
            "date_sanity:reported_before_loss",
            claim.reported_date >= claim.loss_date,
            expected="reported >= loss",
            actual=f"{claim.reported_date} vs {claim.loss_date}",
        )
        if claim.closed_date is not None:
            record(
                "date_sanity:closed_after_reported",
                claim.closed_date >= claim.reported_date,
                expected="closed >= reported",
                actual=f"{claim.closed_date} vs {claim.reported_date}",
            )

        for amount_name in ("total_paid", "total_reserved", "deductible"):
            amount = getattr(claim, amount_name)
            record(
                f"amount_sanity:{amount_name}_non_negative",
                amount >= 0,
                expected=">= 0",
                actual=str(amount),
            )

        expected_incurred = claim.total_paid + claim.total_reserved
        if claim.total_incurred != expected_incurred:
            warnings.append(
                f"claim {claim.claim_id}: total_incurred {claim.total_incurred} "
                f"!= paid+reserved ({expected_incurred})"
            )
            record(
                "amount_sanity:incurred_equals_paid_plus_reserved",
                False,
                expected=str(expected_incurred),
                actual=str(claim.total_incurred),
                severity="warning",
            )
        else:
            record("amount_sanity:incurred_equals_paid_plus_reserved", True)

        for exposure in claim.exposures:
            record(
                "referential_integrity:exposure_claim_id",
                exposure.claim_id == claim.claim_id,
                expected=claim.claim_id,
                actual=exposure.claim_id,
            )
        for claimant in claim.claimants:
            record(
                "referential_integrity:claimant_claim_id",
                claimant.claim_id == claim.claim_id,
                expected=claim.claim_id,
                actual=claimant.claim_id,
            )
        for transaction in claim.transactions:
            record(
                "referential_integrity:transaction_claim_id",
                transaction.claim_id == claim.claim_id,
                expected=claim.claim_id,
                actual=transaction.claim_id,
            )

        record("enum_validity:status", self._check_enum_validity(claim.status, ClaimStatus))
        record("enum_validity:loss_cause", self._check_enum_validity(claim.loss_cause, LossCause))

        return failures, warnings, passed, total

    @staticmethod
    def _check_enum_validity(value: object, enum_cls: type[Enum]) -> bool:
        """Return True if value is a valid member of enum_cls."""
        if isinstance(value, enum_cls):
            return value in enum_cls
        try:
            enum_cls(value)
            return True
        except (ValueError, TypeError):
            return False
