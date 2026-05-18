"""Shared pytest fixtures and session configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.config import setup_logging
from src.schema.base_adapter import BaseAdapter
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
def pytest_configure(config: pytest.Config) -> None:
    """Initialize logging before any tests run."""
    setup_logging()


UTC = timezone.utc


@pytest.fixture
def valid_address() -> Address:
    """Valid US address."""
    return Address(
        street_1="123 Main St",
        city="Newark",
        state="NJ",
        postal_code="07302",
        country="US",
    )


@pytest.fixture
def valid_policy(valid_address: Address) -> PolicySnapshot:
    """Valid policy snapshot with coverages."""
    return PolicySnapshot(
        policy_number="POL-100",
        carrier_name="Example Carrier",
        product_type="Personal Auto",
        effective_date=datetime(2024, 1, 1, tzinfo=UTC),
        expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
        insured_name="Jane Doe",
        coverages=[
            Coverage(
                coverage_type="Collision",
                limit=Decimal("50000"),
                deductible=Decimal("500"),
                premium=Decimal("1200"),
            )
        ],
        premium=Decimal("1200"),
    )


@pytest.fixture
def valid_claim(valid_address: Address) -> Claim:
    """Fully populated claim with nested entities."""
    claim_id = "CLM-001"
    return Claim(
        claim_id=claim_id,
        claim_number="2024-0001",
        status=ClaimStatus.OPEN,
        loss_date=datetime(2024, 3, 1, 12, 0, tzinfo=UTC),
        reported_date=datetime(2024, 3, 2, 9, 0, tzinfo=UTC),
        loss_description="Rear-end collision",
        loss_cause=LossCause.COLLISION,
        loss_location=valid_address,
        line_of_business=LineOfBusiness.PERSONAL_AUTO,
        policy_number="POL-100",
        policy_effective_date=datetime(2024, 1, 1, tzinfo=UTC),
        policy_expiration_date=datetime(2025, 1, 1, tzinfo=UTC),
        total_incurred=Decimal("15000"),
        total_paid=Decimal("5000"),
        total_reserved=Decimal("10000"),
        deductible=Decimal("500"),
        created_at=datetime(2024, 3, 2, 10, 0, tzinfo=UTC),
        updated_at=datetime(2024, 3, 2, 10, 0, tzinfo=UTC),
        source_system="test_carrier",
        raw_data={"source": "fixture"},
        exposures=[
            Exposure(
                exposure_id="EXP-1",
                claim_id=claim_id,
                exposure_type=ExposureType.VEHICLE_DAMAGE,
                coverage_type="Collision",
                status=ExposureStatus.OPEN,
                reserved_amount=Decimal("8000"),
                paid_amount=Decimal("3000"),
                deductible_amount=Decimal("500"),
                claimant_id="CLMT-1",
            ),
            Exposure(
                exposure_id="EXP-2",
                claim_id=claim_id,
                exposure_type=ExposureType.BODILY_INJURY,
                coverage_type="BI",
                reserved_amount=Decimal("7000"),
                paid_amount=Decimal("2000"),
                deductible_amount=Decimal("0"),
                claimant_id="CLMT-2",
            ),
        ],
        claimants=[
            Claimant(
                claimant_id="CLMT-1",
                claim_id=claim_id,
                role=ContactRole.CLAIMANT,
                first_name="John",
                last_name="Driver",
            ),
            Claimant(
                claimant_id="CLMT-2",
                claim_id=claim_id,
                role=ContactRole.INSURED,
                first_name="Jane",
                last_name="Doe",
            ),
        ],
        transactions=[
            Transaction(
                transaction_id="TXN-1",
                claim_id=claim_id,
                exposure_id="EXP-1",
                transaction_type=TransactionType.PAYMENT,
                amount=Decimal("3000"),
                transaction_date=datetime(2024, 3, 10, tzinfo=UTC),
                status=TransactionStatus.POSTED,
            ),
            Transaction(
                transaction_id="TXN-2",
                claim_id=claim_id,
                exposure_id="EXP-2",
                transaction_type=TransactionType.RESERVE_SET,
                amount=Decimal("7000"),
                transaction_date=datetime(2024, 3, 5, tzinfo=UTC),
            ),
            Transaction(
                transaction_id="TXN-3",
                claim_id=claim_id,
                transaction_type=TransactionType.RECOVERY,
                amount=Decimal("-500"),
                transaction_date=datetime(2024, 3, 15, tzinfo=UTC),
            ),
        ],
    )


class MockAdapter(BaseAdapter):
    """Minimal adapter for testing transform_batch."""

    @property
    def name(self) -> str:
        return "Mock Test Adapter"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def source_system(self) -> str:
        return "mock"

    @property
    def supported_formats(self) -> list[str]:
        return ["json"]

    def parse_raw(self, raw_input: str | bytes) -> list[dict[str, object]]:
        """Parse JSON array or single object into raw records."""
        text = raw_input.decode() if isinstance(raw_input, bytes) else raw_input
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return [data]

    def map_record(self, raw_record: dict[str, object]) -> dict[str, object]:
        """Pass through mapped records (already universal shape in tests)."""
        return raw_record


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Mock adapter instance."""
    return MockAdapter()


def claim_to_mapped_dict(claim: Claim) -> dict[str, object]:
    """Serialize claim to dict for adapter tests (Python mode for strict validation)."""
    return claim.model_dump()


@pytest.fixture(autouse=True)
def discovery_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set GEMINI_API_KEY for discovery tests that hit validate_gemini_config."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import src.config as config_module

    config_module._settings = None


@pytest.fixture
def sample_json_claims() -> str:
    """Guidewire-style JSON with three claims and nested exposures."""
    return json.dumps(
        [
            {
                "claimId": "GW-001",
                "lossDate": "2024-01-15",
                "claimStatus": "open",
                "exposures": [{"exposureType": "BI", "reservedAmount": 5000}],
            },
            {
                "claimId": "GW-002",
                "lossDate": "2024-02-01",
                "claimStatus": "closed",
                "exposures": [{"exposureType": "PD", "reservedAmount": 1200}],
            },
            {
                "claimId": "GW-003",
                "lossDate": "2024-03-10",
                "claimStatus": "open",
                "exposures": [],
            },
        ]
    )


@pytest.fixture
def sample_xml_claims() -> str:
    """ACORD-like XML with two claims."""
    return (
        '<?xml version="1.0"?>'
        '<ACORD xmlns="http://www.ACORD.org/standards/PC_Surety/ACORD1/xml/" Version="2.0">'
        "<Claims>"
        '<Claim><ClaimId>C1</ClaimId><LossDt>2024-01-01</LossDt></Claim>'
        '<Claim><ClaimId>C2</ClaimId><LossDt>2024-02-01</LossDt></Claim>'
        "</Claims></ACORD>"
    )


@pytest.fixture
def sample_csv_claims() -> str:
    """Pipe-delimited legacy CSV with four claims."""
    return (
        "CLM_ID|CLMNT_NM|DT_OF_LSS|STATUS\n"
        "1001|SMITH|20240115|OPEN\n"
        "1002|JONES|20240201|CLOSED\n"
        "1003|LEE|20240301|OPEN\n"
        "1004|PARK|20240401|OPEN\n"
    )


@pytest.fixture
def sample_data_dictionary() -> str:
    """Markdown data dictionary with ten fields."""
    return (
        "| Field | Type | Description |\n"
        "| --- | --- | --- |\n"
        "| claimId | string | Unique claim identifier |\n"
        "| lossDate | date | Date of loss |\n"
        "| claimStatus | string | Claim status code |\n"
        "| exposureType | string | Exposure type |\n"
        "| reservedAmount | decimal | Reserve amount |\n"
        "| CLM_ID | string | Legacy claim ID |\n"
        "| CLMNT_NM | string | Claimant name |\n"
        "| DT_OF_LSS | date | Date of loss (legacy) |\n"
        "| STATUS | string | Legacy status |\n"
        "| extraDocField | string | Field only in dictionary |\n"
    )


@pytest.fixture
def mock_field_analyzer() -> object:
    """Analyzer that annotates fields without calling Gemini."""
    from src.discovery.profile import FieldInfo

    class _StubAnalyzer:
        async def annotate_fields(
            self,
            fields: list[FieldInfo],
            source_format: str,
            notes: list[str],
        ) -> list[FieldInfo]:
            del source_format, notes
            return [
                f.model_copy(
                    update={
                        "insurance_annotation": f"annotated {f.source_name}",
                        "confidence": 0.9,
                    }
                )
                for f in fields
            ]

    return _StubAnalyzer()


@pytest.fixture
def tmp_knowledge_base(tmp_path: object) -> object:
    """Knowledge base rooted at a temporary directory."""
    from pathlib import Path

    from src.mapping.knowledge_base import MappingKnowledgeBase

    return MappingKnowledgeBase(Path(str(tmp_path)) / "kb")


@pytest.fixture
def guidewire_profile() -> object:
    """Guidewire-style ClientProfile for mapping tests."""
    from src.discovery.profile import ClientProfile, FieldInfo

    fields = [
        FieldInfo(source_name="claimId", inferred_type="string", sample_values=["GW-001"]),
        FieldInfo(source_name="lossDate", inferred_type="date", sample_values=["2024-01-15"]),
        FieldInfo(
            source_name="claimStatus",
            inferred_type="string",
            sample_values=["open"],
        ),
        FieldInfo(
            source_name="reportedDate",
            inferred_type="date",
            sample_values=["2024-01-16"],
        ),
        FieldInfo(source_name="claimNumber", inferred_type="string", sample_values=["2024-1"]),
        FieldInfo(
            source_name="lossDescription",
            inferred_type="string",
            sample_values=["Collision"],
        ),
        FieldInfo(source_name="policyNumber", inferred_type="string", sample_values=["POL-1"]),
        FieldInfo(
            source_name="totalIncurred",
            inferred_type="decimal",
            sample_values=["10000"],
        ),
        FieldInfo(source_name="assignedGroup", inferred_type="string", sample_values=["TeamA"]),
    ]
    return ClientProfile(
        client_name="guidewire_carrier",
        source_format="json",
        detected_encoding="utf-8",
        total_records_sampled=3,
        total_fields_detected=len(fields),
        fields=fields,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def legacy_profile() -> object:
    """Legacy mainframe-style ClientProfile."""
    from src.discovery.profile import ClientProfile, FieldInfo

    fields = [
        FieldInfo(source_name="CLM_NBR", inferred_type="string", sample_values=["1001"]),
        FieldInfo(source_name="DT_OF_LSS", inferred_type="string", sample_values=["20240115"]),
        FieldInfo(source_name="CLMNT_LST_NM", inferred_type="string", sample_values=["SMITH"]),
        FieldInfo(source_name="STATUS", inferred_type="string", sample_values=["OPEN"]),
        FieldInfo(source_name="RSV_AMT", inferred_type="string", sample_values=["5000"]),
    ]
    return ClientProfile(
        client_name="legacy_carrier",
        source_format="csv",
        detected_encoding="utf-8",
        total_records_sampled=4,
        total_fields_detected=len(fields),
        fields=fields,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def acord_profile() -> object:
    """ACORD-style ClientProfile."""
    from src.discovery.profile import ClientProfile, FieldInfo

    fields = [
        FieldInfo(source_name="ClaimId", inferred_type="string", sample_values=["C1"]),
        FieldInfo(source_name="LossDt", inferred_type="string", sample_values=["2024-01-01"]),
        FieldInfo(source_name="ReportedDt", inferred_type="string", sample_values=["2024-01-02"]),
        FieldInfo(source_name="ClaimStatusCd", inferred_type="string", sample_values=["OPN"]),
        FieldInfo(source_name="PolicyNumber", inferred_type="string", sample_values=["P-1"]),
    ]
    return ClientProfile(
        client_name="acord_carrier",
        source_format="xml",
        detected_encoding="utf-8",
        total_records_sampled=2,
        total_fields_detected=len(fields),
        fields=fields,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_semantic_matcher() -> object:
    """Semantic matcher stub for integration tests."""
    from src.mapping.config import FieldMapping, MatchType
    from src.mapping.semantic_matcher import SemanticMatchOutcome, SemanticMatcher

    class _StubSemantic(SemanticMatcher):
        def __init__(self) -> None:
            pass

        async def match(self, unmatched_fields, already_mapped_targets, **kwargs):  # type: ignore[no-untyped-def]
            del already_mapped_targets, kwargs
            mappings = []
            gaps = []
            legacy_map = {
                "CLMNT_LST_NM": ("claimant.last_name", 0.75),
                "DT_OF_LSS": ("claim.loss_date", 0.8),
            }
            for field in unmatched_fields:
                entry = legacy_map.get(field.source_name)
                if entry:
                    target, conf = entry
                    mappings.append(
                        FieldMapping(
                            source_field=field.source_name,
                            source_path=field.nesting_path,
                            target_field=target,
                            match_type=MatchType.SEMANTIC,
                            confidence=conf,
                            reasoning="stub semantic match",
                        )
                    )
                else:
                    from src.mapping.config import GapInfo, GapType

                    gaps.append(
                        GapInfo(
                            field_name=field.source_name,
                            gap_type=GapType.UNMAPPED_SOURCE,
                            severity="warning",
                            description="no stub match",
                        )
                    )
            return SemanticMatchOutcome(mappings=mappings, gaps=gaps)

    return _StubSemantic()
