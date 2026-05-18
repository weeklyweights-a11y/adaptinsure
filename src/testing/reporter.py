"""Test report generation and persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.exceptions import TestHarnessError
from src.testing.codes import TEST_REPORT_WRITE_FAILED
from src.testing.contract_tests import ContractTestResult
from src.testing.roundtrip import RoundTripResult

OverallStatus = Literal["pass", "warn", "fail"]


class EdgeCaseSummary(BaseModel):
    """Summary of edge case run outcomes."""

    model_config = ConfigDict(strict=True)

    total: int = 0
    passed: int = 0
    failed_expected: int = 0
    failed_unexpected: int = 0


class TestReport(BaseModel):
    """Full harness report."""

    model_config = ConfigDict(strict=True)

    overall_status: OverallStatus = "pass"
    contract: ContractTestResult
    roundtrip: RoundTripResult
    edge_cases: EdgeCaseSummary | None = None
    recommendations: list[str] = Field(default_factory=list)


class TestReporter:
    """Builds human-readable and JSON test reports."""

    def generate_report(
        self,
        contract_result: ContractTestResult,
        roundtrip_result: RoundTripResult,
        edge_case_results: dict[str, int] | None = None,
    ) -> TestReport:
        """Aggregate results into a TestReport."""
        edge_summary: EdgeCaseSummary | None = None
        if edge_case_results:
            edge_summary = EdgeCaseSummary(
                total=sum(edge_case_results.values()),
                passed=edge_case_results.get("passed", 0),
                failed_expected=edge_case_results.get("failed_expected", 0),
                failed_unexpected=edge_case_results.get("failed_unexpected", 0),
            )

        status: OverallStatus = "pass"
        if contract_result.pass_rate < 0.80:
            status = "fail"
        elif contract_result.failed_checks > 0 or contract_result.warnings:
            status = "warn"
        elif roundtrip_result.field_survival_rate < 0.85:
            status = "warn"

        recommendations = self._recommendations(contract_result, roundtrip_result)
        return TestReport(
            overall_status=status,
            contract=contract_result,
            roundtrip=roundtrip_result,
            edge_cases=edge_summary,
            recommendations=recommendations,
        )

    def format_report(self, report: TestReport) -> str:
        """Format report as plain text."""
        lines = [
            "=== AdaptInsure Test Report ===",
            f"Overall status: {report.overall_status.upper()}",
            "",
            "--- Contract Tests ---",
            f"Claims: {report.contract.total_claims} "
            f"(passed {report.contract.passed_claims}, "
            f"failed {report.contract.failed_claims})",
            f"Checks: {report.contract.total_checks} "
            f"(pass rate {report.contract.pass_rate:.2%})",
            f"Failures: {len(report.contract.failures)}",
            "",
            "--- Round-Trip ---",
            f"Records: {report.roundtrip.total_records}",
            f"Field survival rate: {report.roundtrip.field_survival_rate:.2%}",
            f"Survived: {report.roundtrip.fields_survived}, "
            f"Lost: {report.roundtrip.fields_lost}, "
            f"Transformed: {report.roundtrip.fields_transformed}",
        ]
        if report.edge_cases:
            lines.extend(
                [
                    "",
                    "--- Edge Cases ---",
                    f"Total: {report.edge_cases.total}",
                    f"Passed: {report.edge_cases.passed}",
                    f"Failed (expected): {report.edge_cases.failed_expected}",
                    f"Failed (unexpected): {report.edge_cases.failed_unexpected}",
                ]
            )
        if report.contract.failures:
            lines.extend(["", "--- Critical Failures ---"])
            for failure in report.contract.failures[:20]:
                if failure.severity == "error":
                    lines.append(
                        f"  {failure.claim_id}: {failure.check_name} "
                        f"(expected {failure.expected}, got {failure.actual})"
                    )
        if report.recommendations:
            lines.extend(["", "--- Recommendations ---"])
            lines.extend(f"  - {rec}" for rec in report.recommendations)
        return "\n".join(lines) + "\n"

    def save_report(self, report: TestReport, output_path: Path) -> None:
        """Write .txt and .json report files."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            txt_path = output_path.with_suffix(".txt")
            json_path = output_path.with_suffix(".json")
            txt_path.write_text(self.format_report(report), encoding="utf-8")
            json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            raise TestHarnessError(
                TEST_REPORT_WRITE_FAILED,
                f"Failed to write report to {output_path}",
                details={"error": str(exc)},
            ) from exc

    @staticmethod
    def _recommendations(
        contract: ContractTestResult,
        roundtrip: RoundTripResult,
    ) -> list[str]:
        recs: list[str] = []
        date_failures = [
            f for f in contract.failures if f.check_name.startswith("date_sanity:")
        ]
        if len(date_failures) >= 3:
            recs.append("Review date transform mappings — multiple date sanity failures.")
        if roundtrip.field_survival_rate < 0.8:
            recs.append("Low field survival — verify FIELD_MAPPINGS and transforms.")
        amount_failures = [
            f for f in contract.failures if f.check_name.startswith("amount_sanity:")
        ]
        if amount_failures:
            recs.append("Review currency and amount transforms.")
        return recs
