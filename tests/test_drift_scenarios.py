"""Simulated drift scenarios (Phase 6 Step 7)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.discovery.engine import DiscoveryEngine
from src.llm.client import LLMClient
from src.mapping.engine import MappingEngine
from src.monitor.differ import DiffType
from src.monitor.proposer import (
    ConfigChange,
    FixProposer,
    FixType,
    ProposedFixResponse,
)
from tests.monitor.conftest import SAMPLES, build_guidewire_baseline
from tests.testing.pipeline_helpers import _apply_transform_overrides, _filter_claim_mappings
from tests.testing.semantic_stubs import acord_semantic_matcher, legacy_semantic_matcher

SAMPLES_ROOT = SAMPLES


def _mock_proposer() -> FixProposer:
    """FixProposer with deterministic mocked Gemini responses."""
    mock_llm = MagicMock()

    async def _analyze(_s: str, _u: str, output_model: type, **kwargs: object) -> object:
        return output_model.model_validate(
            {
                "fix_type": "update_field_name",
                "description": "proposed fix",
                "config_changes": [
                    {
                        "change_type": "update_field_mapping",
                        "field_path": "lossDate",
                        "old_value": "lossDate",
                        "new_value": "dateOfLoss",
                        "explanation": "rename",
                    }
                ],
                "auto_applicable": True,
                "confidence": 0.95,
                "reasoning": "test",
            }
        )

    mock_llm.analyze = AsyncMock(side_effect=_analyze)
    return FixProposer(mock_llm)


def _records_matching_schema(schema: object, count: int = 5) -> str:
    """Build records that match expected schema sample values."""
    from src.monitor.expected_schema import ExpectedSchema

    assert isinstance(schema, ExpectedSchema)
    record: dict[str, object] = {}
    for field in schema.fields:
        if field.sample_values:
            val: object = field.sample_values[0]
            if field.expected_type == "integer" and str(val).isdigit():
                val = int(str(val))
            record[field.field_name] = val
        elif field.nullable:
            record[field.field_name] = None
        else:
            record[field.field_name] = "sample"
    return json.dumps([dict(record) for _ in range(count)])


def _mutate_records(raw: str, mutator: object) -> str:
    """Apply mutator to each record and return JSON string."""
    records = json.loads(raw)
    out = []
    for rec in records:
        item = copy.deepcopy(rec)
        mutator(item)
        out.append(item)
    return json.dumps(out)


@pytest.mark.asyncio
class TestDriftScenarios:
    """Eight drift scenarios against synthetic insurers."""

    async def test_scenario_1_field_renamed(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """lossDate renamed to dateOfLoss -> field_renamed, critical."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        mutated = _mutate_records(
            bundle["raw"],
            lambda r: r.update({"dateOfLoss": r.pop("lossDate")}),
        )
        detector = bundle["detector"]
        detector._proposer = _mock_proposer()
        report = await detector.check(
            "guidewire_carrier",
            mutated,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        assert report.status == "drifted"
        loss_drifts = [d for d in report.drifts if d.field_name in {"lossDate", "dateOfLoss"}]
        assert loss_drifts
        assert any(
            d.diff_type in {DiffType.FIELD_RENAMED, DiffType.FIELD_REMOVED}
            for d in loss_drifts
        )
        assert report.alerts

    async def test_scenario_2_date_format_changed(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """YYYY-MM-DD -> MM/DD/YYYY format_changed."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        mutated = _mutate_records(
            bundle["raw"],
            lambda r: r.update({"lossDate": "01/15/2024"}),
        )
        report = await bundle["detector"].check(
            "guidewire_carrier",
            mutated,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        assert any(d.diff_type == DiffType.FORMAT_CHANGED for d in report.drifts)

    async def test_scenario_3_optional_field_removed(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """catastropheCode removed -> field_removed warning."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        mutated = _mutate_records(bundle["raw"], lambda r: r.pop("catastropheCode", None))
        report = await bundle["detector"].check(
            "guidewire_carrier",
            mutated,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        removed = [d for d in report.drifts if d.field_name == "catastropheCode"]
        assert removed
        assert removed[0].diff_type == DiffType.FIELD_REMOVED
        assert removed[0].severity == "warning"

    async def test_scenario_4_required_field_removed(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """claimNumber removed -> field_removed critical."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        mutated = _mutate_records(bundle["raw"], lambda r: r.pop("claimNumber", None))
        report = await bundle["detector"].check(
            "guidewire_carrier",
            mutated,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        removed = [d for d in report.drifts if d.field_name == "claimNumber"]
        assert removed
        assert removed[0].severity == "critical"

    async def test_scenario_5_new_field_added(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """processingCenter added -> field_added info."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        mutated = _mutate_records(
            bundle["raw"],
            lambda r: r.update({"processingCenter": "NYC"}),
        )
        report = await bundle["detector"].check(
            "guidewire_carrier",
            mutated,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        added = [d for d in report.drifts if d.diff_type == DiffType.FIELD_ADDED]
        assert added
        assert added[0].severity == "info"

    async def test_scenario_6_enum_value_added(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """One claim claimState suspended -> enum_value_added warning."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        records = json.loads(bundle["raw"])
        records[0]["claimState"] = "suspended"
        report = await bundle["detector"].check(
            "guidewire_carrier",
            json.dumps(records),
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        enum_diffs = [d for d in report.drifts if d.diff_type == DiffType.ENUM_VALUE_ADDED]
        assert enum_diffs
        assert enum_diffs[0].severity == "warning"
        assert enum_diffs[0].affected_records < enum_diffs[0].total_records

    async def test_scenario_7_legacy_type_change(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """DT_OF_LSS int to ISO string -> type or format change critical."""
        from src.testing.legacy_bundler import load_legacy_bundle

        bundle_data = load_legacy_bundle(SAMPLES_ROOT)
        raw = bundle_data.claims_bytes.decode("latin-1")
        llm = LLMClient(api_key="test-key")
        profile = await DiscoveryEngine(
            llm, field_analyzer=mock_field_analyzer
        ).discover(raw, "legacy_carrier")
        matcher = legacy_semantic_matcher()
        mapping_engine = MappingEngine(llm, tmp_knowledge_base, semantic_matcher=matcher)
        config = await mapping_engine.map(profile)
        config = _apply_transform_overrides(config, matcher)
        config = config.model_copy(
            update={"field_mappings": _filter_claim_mappings(config.field_mappings)}
        )
        from src.monitor.config_loader import write_mapping_config
        from src.monitor.detector import DriftDetector

        write_mapping_config(config, monitor_dirs["generated_dir"])
        detector = DriftDetector(schema_dir=monitor_dirs["schema_dir"])
        detector.bootstrap_baseline("legacy_carrier", config, profile)
        records = [dict(r) for r in bundle_data.joined_records]
        for rec in records:
            if "DT_OF_LSS" in rec:
                rec["DT_OF_LSS"] = "2024-01-15"
        report = await detector.check(
            "legacy_carrier",
            json.dumps(records),
            mapping_config=config,
            profile=profile,
        )
        assert report.status == "drifted"
        assert any(
            d.diff_type in {DiffType.TYPE_CHANGED, DiffType.FORMAT_CHANGED}
            for d in report.drifts
        )

    async def test_scenario_8_multiple_drifts_acord(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """ACORD rename + format + new field -> multiple drifts."""
        raw = (SAMPLES_ROOT / "acord_carrier" / "sample_claims.xml").read_text(encoding="utf-8")
        llm = LLMClient(api_key="test-key")
        profile = await DiscoveryEngine(
            llm, field_analyzer=mock_field_analyzer
        ).discover(raw, "acord_carrier")
        matcher = acord_semantic_matcher()
        mapping_engine = MappingEngine(llm, tmp_knowledge_base, semantic_matcher=matcher)
        config = await mapping_engine.map(profile)
        config = _apply_transform_overrides(config, matcher)
        config = config.model_copy(
            update={"field_mappings": _filter_claim_mappings(config.field_mappings)}
        )
        from src.monitor.config_loader import write_mapping_config
        from src.monitor.detector import DriftDetector
        from src.monitor.records import parse_incoming_records

        write_mapping_config(config, monitor_dirs["generated_dir"])
        detector = DriftDetector(schema_dir=monitor_dirs["schema_dir"])
        detector.bootstrap_baseline("acord_carrier", config, profile)
        _fmt, records = parse_incoming_records(raw)
        for rec in records:
            if "LossDt" in rec:
                rec["DateOfLoss"] = rec.pop("LossDt")
                rec["DateOfLoss"] = "01/15/2020"
            rec["NewField"] = "test"
        report = await detector.check(
            "acord_carrier",
            json.dumps(records),
            mapping_config=config,
            profile=profile,
        )
        assert report.drifts_found >= 2

    async def test_no_false_positives_on_unchanged_batch(
        self,
        monitor_dirs: dict,
        mock_field_analyzer: object,
        tmp_knowledge_base: object,
    ) -> None:
        """Unmutated sample returns clean report."""
        bundle = await build_guidewire_baseline(
            monitor_dirs, mock_field_analyzer, tmp_knowledge_base
        )
        clean = _records_matching_schema(bundle["schema"], count=10)
        clean_recs = json.loads(clean)
        aligned_fields = []
        for ef in bundle["schema"].fields:
            val = clean_recs[0].get(ef.field_name)
            samples = [str(val)] if val is not None and val != "" else list(ef.sample_values[:1])
            aligned_fields.append(ef.model_copy(update={"sample_values": samples}))
        aligned_schema = bundle["schema"].model_copy(update={"fields": aligned_fields})
        bundle["detector"].save_expected_schema(aligned_schema)
        report = await bundle["detector"].check(
            "guidewire_carrier",
            clean,
            mapping_config=bundle["config"],
            profile=bundle["profile"],
        )
        assert report.status == "clean"
        assert report.drifts_found == 0
