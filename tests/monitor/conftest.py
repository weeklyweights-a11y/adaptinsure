"""Fixtures for drift scenario integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.discovery.engine import DiscoveryEngine
from src.discovery.profile import ClientProfile
from src.llm.client import LLMClient
from src.mapping.config import MappingConfig
from src.mapping.engine import MappingEngine
from src.monitor.config_loader import write_mapping_config
from src.monitor.detector import DriftDetector
from tests.testing.pipeline_helpers import _apply_transform_overrides, _filter_claim_mappings
from tests.testing.semantic_stubs import guidewire_semantic_matcher

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def monitor_dirs(tmp_path: Path) -> dict[str, Path]:
    """Temporary schema, generated, and pending-fix directories."""
    schema_dir = tmp_path / "schemas"
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True)
    return {
        "schema_dir": schema_dir,
        "generated_dir": generated_dir,
        "pending_path": tmp_path / "pending_fixes.json",
    }


async def build_guidewire_baseline(
    monitor_dirs: dict[str, Path],
    mock_field_analyzer: object,
    tmp_knowledge_base: Path,
) -> dict[str, object]:
    """Discover, map, persist config + expected schema for Guidewire."""
    raw = (SAMPLES / "guidewire_carrier" / "sample_claims.json").read_text(encoding="utf-8")
    llm = LLMClient(api_key="test-key")
    engine = DiscoveryEngine(llm, field_analyzer=mock_field_analyzer)
    profile = await engine.discover(raw, "guidewire_carrier")
    matcher = guidewire_semantic_matcher()
    mapping_engine = MappingEngine(llm, tmp_knowledge_base, semantic_matcher=matcher)
    config = await mapping_engine.map(profile)
    config = _apply_transform_overrides(config, matcher)
    config = config.model_copy(
        update={"field_mappings": _filter_claim_mappings(config.field_mappings)}
    )
    write_mapping_config(config, monitor_dirs["generated_dir"])
    detector = DriftDetector(schema_dir=monitor_dirs["schema_dir"])
    schema = detector.bootstrap_baseline("guidewire_carrier", config, profile)
    return {
        "raw": raw,
        "profile": profile,
        "config": config,
        "schema": schema,
        "detector": detector,
        "dirs": monitor_dirs,
    }


@pytest.fixture
async def guidewire_baseline(
    monitor_dirs: dict[str, Path],
    mock_field_analyzer: object,
    tmp_knowledge_base: Path,
) -> dict[str, object]:
    """Guidewire baseline bundle for drift scenarios."""
    return await build_guidewire_baseline(
        monitor_dirs, mock_field_analyzer, tmp_knowledge_base
    )
