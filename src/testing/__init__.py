"""Test harness for validating generated adapters."""

from src.testing.contract_tests import (
    ContractFailure,
    ContractTestResult,
    ContractTestRunner,
)
from src.testing.edge_cases import EdgeCase, EdgeCaseGenerator, EdgeCaseRunner
from src.testing.legacy_bundler import LegacyBundle, load_legacy_bundle
from src.testing.reporter import EdgeCaseSummary, TestReport, TestReporter
from src.testing.roundtrip import LostField, RoundTripResult, RoundTripValidator

__all__ = [
    "ContractFailure",
    "ContractTestResult",
    "ContractTestRunner",
    "EdgeCase",
    "EdgeCaseGenerator",
    "EdgeCaseRunner",
    "EdgeCaseSummary",
    "LegacyBundle",
    "LostField",
    "RoundTripResult",
    "RoundTripValidator",
    "TestReport",
    "TestReporter",
    "load_legacy_bundle",
]
