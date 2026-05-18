"""Tests for the Drift Monitor (Phase 6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.discovery.profile import ClientProfile, FieldInfo
from src.exceptions import LLMError, MonitorError
from src.mapping.config import (
    ConfidenceSummary,
    FieldMapping,
    FieldTransform,
    MappingConfig,
    MatchType,
    TransformType,
)
from src.mapping.schema_registry import CRITICAL_REQUIRED_TARGETS
from src.monitor.alerter import AlertGenerator
from src.monitor.approval import ApprovalWorkflow
from src.monitor.config_applier import apply_config_changes
from src.monitor.differ import DiffType, SchemaDiffer
from src.monitor.detector import DriftDetector
from src.monitor.expected_schema import ExpectedSchema
from src.monitor.proposer import (
    ConfigChange,
    FixProposer,
    FixType,
    ProposedFixResponse,
)
from src.monitor.differ import SchemaDiff



def _summary() -> ConfidenceSummary:
    return ConfidenceSummary(
        total_fields=2,
        mapped_fields=2,
        unmapped_fields=0,
        high_confidence_count=2,
        medium_confidence_count=0,
        low_confidence_count=0,
        average_confidence=0.9,
    )


def _profile(fields: list[FieldInfo] | None = None) -> ClientProfile:
    flds = fields or [
        FieldInfo(
            source_name="lossDate",
            inferred_type="date",
            sample_values=["2024-01-15"],
            nullable=False,
            format_pattern="YYYY-MM-DD",
        ),
        FieldInfo(
            source_name="claimNumber",
            inferred_type="string",
            sample_values=["CLM-1"],
            nullable=False,
        ),
    ]
    return ClientProfile(
        client_name="test_carrier",
        source_format="json",
        detected_encoding="utf-8",
        total_records_sampled=10,
        total_fields_detected=len(flds),
        fields=flds,
        created_at=datetime.now(UTC),
    )


def _config() -> MappingConfig:
    return MappingConfig(
        client_name="test_carrier",
        source_format="json",
        schema_version="1.0.0",
        field_mappings=[
            FieldMapping(
                source_field="lossDate",
                target_field="claim.loss_date",
                match_type=MatchType.DIRECT,
                confidence=0.95,
                reasoning="match",
                transform=FieldTransform(
                    transform_type=TransformType.DATE_FORMAT,
                    source_format="YYYY-MM-DD",
                    target_format="ISO 8601",
                ),
            ),
            FieldMapping(
                source_field="claimNumber",
                target_field="claim.claim_number",
                match_type=MatchType.DIRECT,
                confidence=0.95,
                reasoning="match",
            ),
            FieldMapping(
                source_field="catastropheCode",
                target_field="claim.catastrophe_code",
                match_type=MatchType.DIRECT,
                confidence=0.8,
                reasoning="optional",
            ),
        ],
        transforms=[],
        gaps=[],
        confidence_summary=_summary(),
        created_at=datetime.now(UTC),
    )


class TestExpectedSchema:
    """ExpectedSchema builder tests (spec Step 1)."""

    def test_expected_schema_creates(self) -> None:
        """ExpectedSchema creates with all fields."""
        schema = ExpectedSchema(
            client_name="c",
            source_format="json",
            fields=[],
            created_at=datetime.now(UTC),
            last_validated_at=datetime.now(UTC),
            record_count_baseline=5,
        )
        assert schema.client_name == "c"

    def test_expected_field_creates(self) -> None:
        """ExpectedField with required attributes creates."""
        from src.monitor.expected_schema import ExpectedField

        field = ExpectedField(
            field_name="lossDate",
            target_field="claim.loss_date",
            expected_type="date",
            required=True,
            nullable=False,
        )
        assert field.field_name == "lossDate"

    def test_from_mapping_config_field_count(self) -> None:
        """from_mapping_config produces correct field count."""
        schema = ExpectedSchema.from_mapping_config(_config(), _profile())
        assert len(schema.fields) == 3

    def test_from_mapping_config_expected_type(self) -> None:
        """from_mapping_config populates expected_type from profile."""
        schema = ExpectedSchema.from_mapping_config(_config(), _profile())
        loss = next(f for f in schema.fields if f.field_name == "lossDate")
        assert loss.expected_type == "date"

    def test_from_mapping_config_expected_format(self) -> None:
        """from_mapping_config populates expected_format."""
        schema = ExpectedSchema.from_mapping_config(_config(), _profile())
        loss = next(f for f in schema.fields if f.field_name == "lossDate")
        assert loss.expected_format == "YYYY-MM-DD"

    def test_from_mapping_config_required_from_nullable(self) -> None:
        """required reflects non-nullable profile fields."""
        schema = ExpectedSchema.from_mapping_config(_config(), _profile())
        loss = next(f for f in schema.fields if f.field_name == "lossDate")
        assert loss.required is True

    def test_empty_fields_list(self) -> None:
        """Empty fields list is valid."""
        schema = ExpectedSchema(
            client_name="empty",
            source_format="json",
            fields=[],
            created_at=datetime.now(UTC),
            last_validated_at=datetime.now(UTC),
            record_count_baseline=0,
        )
        assert schema.fields == []


class TestSchemaDiffer:
    """SchemaDiffer tests (spec Step 2)."""

    def _expected(self) -> ExpectedSchema:
        from src.monitor.expected_schema import ExpectedField

        return ExpectedSchema(
            client_name="t",
            source_format="json",
            fields=[
                ExpectedField(
                    field_name="lossDate",
                    target_field="claim.loss_date",
                    expected_type="date",
                    expected_format="YYYY-MM-DD",
                    required=True,
                    nullable=False,
                    sample_values=["2024-01-15"],
                ),
                ExpectedField(
                    field_name="claimNumber",
                    target_field="claim.claim_number",
                    expected_type="string",
                    required=True,
                    nullable=False,
                    sample_values=["CLM-1"],
                ),
                ExpectedField(
                    field_name="claimState",
                    target_field="claim.status",
                    expected_type="string",
                    enum_values=["open", "closed"],
                    nullable=False,
                    sample_values=["open"],
                ),
                ExpectedField(
                    field_name="amount",
                    target_field="claim.amount",
                    expected_type="integer",
                    nullable=True,
                    sample_values=["100", "100", "100"],
                ),
            ],
            created_at=datetime.now(UTC),
            last_validated_at=datetime.now(UTC),
            record_count_baseline=10,
        )

    def test_no_drift_empty_list(self) -> None:
        """Identical data returns no diffs."""
        records = [
            {
                "lossDate": "2024-01-15",
                "claimNumber": "CLM-1",
                "claimState": "open",
                "amount": 100,
            }
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert diffs == []

    def test_field_removed(self) -> None:
        """Absent key across all records is field_removed."""
        records = [{"claimNumber": "CLM-1", "claimState": "open"}] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        types = [d.diff_type for d in diffs]
        assert DiffType.FIELD_REMOVED in types

    def test_field_renamed(self) -> None:
        """Rename detected with suggested_rename."""
        records = [
            {
                "dateOfLoss": "2024-01-15",
                "claimNumber": "CLM-1",
                "claimState": "open",
                "amount": 100,
            }
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        renamed = [d for d in diffs if d.diff_type == DiffType.FIELD_RENAMED]
        assert renamed
        assert renamed[0].suggested_rename == "dateOfLoss"

    def test_field_added(self) -> None:
        """New consistent field is field_added."""
        records = [
            {
                "lossDate": "2024-01-15",
                "claimNumber": "CLM-1",
                "claimState": "open",
                "newField": "x",
            }
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert any(d.diff_type == DiffType.FIELD_ADDED for d in diffs)

    def test_type_changed(self) -> None:
        """Integer to string triggers type_changed."""
        records = [
            {"lossDate": "2024-01-15", "claimNumber": 123, "claimState": "open", "amount": 100}
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert any(d.diff_type == DiffType.TYPE_CHANGED for d in diffs)

    def test_format_changed(self) -> None:
        """Date format change detected."""
        records = [
            {"lossDate": "01/15/2024", "claimNumber": "CLM-1", "claimState": "open", "amount": 100}
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert any(d.diff_type == DiffType.FORMAT_CHANGED for d in diffs)

    def test_enum_value_added(self) -> None:
        """New enum value detected."""
        records = [
            {"lossDate": "2024-01-15", "claimNumber": "CLM-1", "claimState": "suspended", "amount": 100}
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert any(d.diff_type == DiffType.ENUM_VALUE_ADDED for d in diffs)

    def test_nullable_changed_partial(self) -> None:
        """Single record missing required field is not field_removed."""
        records = [{"lossDate": "2024-01-15", "claimNumber": "CLM-1", "claimState": "open", "amount": 100}] * 19
        records.append({"claimNumber": "CLM-2", "claimState": "open", "amount": 100})
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert not any(
            d.diff_type == DiffType.FIELD_REMOVED and d.field_name == "lossDate" for d in diffs
        )

    def test_multiple_drifts(self) -> None:
        """Multiple drift types in one batch."""
        records = [{"dateOfLoss": "01/15/2024", "claimState": "suspended", "extra": "v"}] * 3
        diffs = SchemaDiffer().diff(self._expected(), records)
        assert len(diffs) >= 2

    def test_removed_required_critical(self) -> None:
        """Removed mapped-required field is critical."""
        records = [{"lossDate": "2024-01-15", "claimState": "open"}] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        removed = [d for d in diffs if d.field_name == "claimNumber"]
        assert removed
        assert removed[0].severity == "critical"
        assert removed[0].target_field in CRITICAL_REQUIRED_TARGETS

    def test_added_field_info(self) -> None:
        """Added field severity is info."""
        records = [
            {"lossDate": "2024-01-15", "claimNumber": "CLM-1", "claimState": "open", "extra": "v"}
        ] * 5
        diffs = SchemaDiffer().diff(self._expected(), records)
        added = [d for d in diffs if d.diff_type == DiffType.FIELD_ADDED]
        assert added[0].severity == "info"

    def test_high_confidence_consistent_drift(self) -> None:
        """Consistent drift has confidence above 0.9."""
        records = [
            {
                "dateOfLoss": "2024-01-15",
                "claimNumber": "CLM-1",
                "claimState": "open",
                "amount": 100,
            }
        ] * 10
        diffs = SchemaDiffer().diff(self._expected(), records)
        renamed = [d for d in diffs if d.diff_type == DiffType.FIELD_RENAMED]
        assert renamed[0].confidence >= 0.9

    def test_distribution_shifted(self) -> None:
        """Numeric distribution shift emits info drift."""
        from src.monitor.expected_schema import ExpectedField

        schema = ExpectedSchema(
            client_name="t",
            source_format="json",
            fields=[
                ExpectedField(
                    field_name="amount",
                    target_field="claim.amount",
                    expected_type="integer",
                    sample_values=["100", "110"],
                    nullable=True,
                ),
            ],
            created_at=datetime.now(UTC),
            last_validated_at=datetime.now(UTC),
            record_count_baseline=5,
        )
        records = [{"amount": 500}] * 5
        diffs = SchemaDiffer().diff(schema, records)
        assert any(d.diff_type == DiffType.DISTRIBUTION_SHIFTED for d in diffs)


class TestAlertGenerator:
    """AlertGenerator tests (spec Step 3)."""

    def _diff(self, severity: str, dtype: DiffType) -> SchemaDiff:
        return SchemaDiff(
            diff_type=dtype,
            field_name="lossDate",
            severity=severity,
            description="test drift",
            affected_records=5,
            total_records=5,
            confidence=1.0,
            target_field="claim.loss_date",
        )

    def test_critical_prefix(self) -> None:
        """Critical alert has CRITICAL prefix."""
        alerts = AlertGenerator().generate_alerts(
            [self._diff("critical", DiffType.FIELD_REMOVED)],
            "client",
        )
        assert "CRITICAL:" in alerts[0].title

    def test_warning_prefix(self) -> None:
        """Warning alert has WARNING prefix."""
        alerts = AlertGenerator().generate_alerts(
            [self._diff("warning", DiffType.ENUM_VALUE_ADDED)],
            "client",
        )
        assert "WARNING:" in alerts[0].title

    def test_info_prefix(self) -> None:
        """Info alert has INFO prefix."""
        alerts = AlertGenerator().generate_alerts(
            [self._diff("info", DiffType.FIELD_ADDED)],
            "client",
        )
        assert "INFO:" in alerts[0].title

    def test_description_has_counts(self) -> None:
        """Description includes record counts."""
        alerts = AlertGenerator().generate_alerts(
            [self._diff("critical", DiffType.FIELD_REMOVED)],
            "client",
        )
        assert "5/5" in alerts[0].description

    def test_unique_alert_ids(self) -> None:
        """Each alert has unique id."""
        diffs = [
            self._diff("info", DiffType.FIELD_ADDED),
            SchemaDiff(
                diff_type=DiffType.FIELD_ADDED,
                field_name="x",
                severity="info",
                description="d",
                affected_records=1,
                total_records=1,
                confidence=1.0,
            ),
        ]
        alerts = AlertGenerator().generate_alerts(diffs, "client")
        assert len({a.alert_id for a in alerts}) == len(alerts)

    def test_defaults_not_acknowledged(self) -> None:
        """acknowledged and resolved default False."""
        alerts = AlertGenerator().generate_alerts(
            [self._diff("warning", DiffType.ENUM_VALUE_ADDED)],
            "client",
        )
        assert alerts[0].acknowledged is False
        assert alerts[0].resolved is False


class TestFixProposer:
    """FixProposer tests with mocked Gemini (spec Step 4)."""

    @pytest.mark.asyncio
    async def test_rename_fix(self) -> None:
        """Renamed field proposes update_field_name."""
        mock = MagicMock()
        mock.analyze = AsyncMock(
            return_value=ProposedFixResponse(
                fix_type=FixType.UPDATE_FIELD_NAME,
                description="rename",
                config_changes=[
                    ConfigChange(
                        change_type="update_field_mapping",
                        field_path="lossDate",
                        old_value="lossDate",
                        new_value="dateOfLoss",
                        explanation="rename",
                    )
                ],
                auto_applicable=True,
                confidence=0.95,
                reasoning="obvious rename",
            )
        )
        diff = SchemaDiff(
            diff_type=DiffType.FIELD_RENAMED,
            field_name="lossDate",
            severity="critical",
            description="renamed",
            suggested_rename="dateOfLoss",
            affected_records=5,
            total_records=5,
            confidence=0.95,
        )
        fix = await FixProposer(mock).propose_fix(diff, _config(), ExpectedSchema.from_mapping_config(_config(), _profile()))
        assert fix.fix_type == FixType.UPDATE_FIELD_NAME
        assert fix.auto_applicable is True

    @pytest.mark.asyncio
    async def test_llm_retry_raises(self) -> None:
        """Invalid LLM response twice raises LLMError."""
        mock = MagicMock()
        mock.analyze = AsyncMock(side_effect=LLMError("LLM_VALIDATION_FAILED", "fail"))
        diff = SchemaDiff(
            diff_type=DiffType.FIELD_REMOVED,
            field_name="claimNumber",
            severity="critical",
            description="removed",
            affected_records=5,
            total_records=5,
            confidence=1.0,
        )
        with pytest.raises(LLMError):
            await FixProposer(mock).propose_fix(
                diff, _config(), ExpectedSchema.from_mapping_config(_config(), _profile())
            )


class TestApprovalWorkflow:
    """ApprovalWorkflow tests (spec Step 5)."""

    def test_submit_pending(self, tmp_path: Path) -> None:
        """Submit creates pending fix."""
        wf = ApprovalWorkflow(pending_path=tmp_path / "pending.json")
        diff = SchemaDiff(
            diff_type=DiffType.FIELD_ADDED,
            field_name="x",
            severity="info",
            description="d",
            affected_records=1,
            total_records=1,
            confidence=1.0,
        )
        from src.monitor.alerter import Alert
        from src.monitor.proposer import ProposedFix

        fix = ProposedFix(
            diff=diff,
            fix_type=FixType.ADD_MAPPING,
            description="add",
            config_changes=[],
            auto_applicable=False,
            confidence=0.5,
            reasoning="r",
        )
        alert = Alert(
            alert_id="aid-1",
            client_name="test_carrier",
            severity="info",
            title="INFO: x",
            description="d",
            diff=diff,
            created_at=datetime.now(UTC),
        )
        wf.submit(fix, alert)
        pending = wf.list_pending()
        assert len(pending) == 1
        assert pending[0].status == "pending"

    def test_submit_auto_approved(self, tmp_path: Path) -> None:
        """auto_applicable fix gets auto_approved status."""
        wf = ApprovalWorkflow(pending_path=tmp_path / "pending.json")
        diff = SchemaDiff(
            diff_type=DiffType.FIELD_RENAMED,
            field_name="lossDate",
            severity="critical",
            description="d",
            affected_records=5,
            total_records=5,
            confidence=1.0,
        )
        from src.monitor.alerter import Alert
        from src.monitor.proposer import ProposedFix

        fix = ProposedFix(
            diff=diff,
            fix_type=FixType.UPDATE_FIELD_NAME,
            description="rename",
            config_changes=[
                ConfigChange(
                    change_type="update_field_mapping",
                    field_path="lossDate",
                    old_value="lossDate",
                    new_value="dateOfLoss",
                    explanation="rename",
                )
            ],
            auto_applicable=True,
            confidence=0.95,
            reasoning="r",
        )
        alert = Alert(
            alert_id="aid-2",
            client_name="test_carrier",
            severity="critical",
            title="CRITICAL",
            description="d",
            diff=diff,
            created_at=datetime.now(UTC),
        )
        wf.submit(fix, alert)
        assert wf.list_pending()[0].status == "auto_approved"

    def test_config_rename_apply(self) -> None:
        """update_field_mapping renames source field."""
        config = _config()
        updated = apply_config_changes(
            config,
            [
                ConfigChange(
                    change_type="update_field_mapping",
                    field_path="lossDate",
                    old_value="lossDate",
                    new_value="dateOfLoss",
                    explanation="rename",
                )
            ],
            FixType.UPDATE_FIELD_NAME,
        )
        names = {m.source_field for m in updated.field_mappings}
        assert "dateOfLoss" in names
        assert "lossDate" not in names

    def test_reject_raises_not_found(self, tmp_path: Path) -> None:
        """Reject unknown fix_id raises MonitorError."""
        wf = ApprovalWorkflow(pending_path=tmp_path / "pending.json")
        with pytest.raises(MonitorError):
            wf.reject("missing", "no")


class TestDriftDetector:
    """DriftDetector tests (spec Step 6)."""

    @pytest.mark.asyncio
    async def test_clean_report(self, tmp_path: Path) -> None:
        """Clean data returns status clean."""
        detector = DriftDetector(schema_dir=tmp_path / "schemas")
        profile = _profile()
        config = _config()
        detector.bootstrap_baseline("test_carrier", config, profile)
        data = json.dumps(
            [{"lossDate": "2024-01-15", "claimNumber": "CLM-1", "catastropheCode": None}]
            * 3
        )
        report = await detector.check("test_carrier", data, mapping_config=config, profile=profile)
        assert report.status == "clean"
        assert report.drifts_found == 0

    @pytest.mark.asyncio
    async def test_missing_schema_raises(self, tmp_path: Path) -> None:
        """Missing expected schema raises MonitorError."""
        detector = DriftDetector(schema_dir=tmp_path / "schemas")
        with pytest.raises(MonitorError):
            await detector.check("unknown", "[]")

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Save and load expected schema round-trips."""
        detector = DriftDetector(schema_dir=tmp_path / "schemas")
        schema = ExpectedSchema.from_mapping_config(_config(), _profile())
        detector.save_expected_schema(schema)
        loaded = detector.load_expected_schema("test_carrier")
        assert loaded.client_name == schema.client_name
