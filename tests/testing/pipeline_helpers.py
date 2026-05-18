"""Shared helpers for full pipeline integration tests."""

from __future__ import annotations

from pathlib import Path

from src.discovery.engine import DiscoveryEngine
from src.generator.engine import GeneratorEngine
from src.generator.registry import AdapterRegistry
from src.llm.client import LLMClient
from src.mapping.engine import MappingEngine
from src.mapping.semantic_matcher import SemanticMatcher
from src.testing.contract_tests import ContractTestRunner
from src.testing.edge_cases import EdgeCaseGenerator, EdgeCaseRunner
from src.testing.legacy_bundler import LegacyBundle, load_legacy_bundle
from src.testing.reporter import TestReporter
from src.testing.roundtrip import RoundTripValidator

_SKIP_SOURCE_FIELDS = frozenset(
    {
        "exposures",
        "contacts",
        "transactions",
        "closedDate",
        "CLS_DT",
        "exposureId",
        "contactId",
        "transactionId",
    }
)


def _filter_claim_mappings(mappings: list) -> list:
    """Keep claim-level mappings only (Strategy A); dedupe by source_field."""
    filtered = [
        m
        for m in mappings
        if m.target_field.startswith("claim.")
        and m.source_field not in _SKIP_SOURCE_FIELDS
    ]
    by_source: dict[str, object] = {}
    for mapping in filtered:
        prev = by_source.get(mapping.source_field)
        if prev is None:
            by_source[mapping.source_field] = mapping
        elif mapping.target_field == "claim.claim_id":
            by_source[mapping.source_field] = mapping
        elif getattr(prev, "target_field", "") != "claim.claim_id":
            by_source[mapping.source_field] = mapping
    return list(by_source.values())


def _apply_transform_overrides(config: object, semantic_matcher: SemanticMatcher) -> object:
    """Attach stub transforms for enum/date fields when direct match omitted them."""
    targets = getattr(semantic_matcher, "_targets", None)
    if not targets:
        return config
    updated = []
    for mapping in config.field_mappings:
        entry = targets.get(mapping.source_field)
        if entry:
            target_field, _confidence, transform = entry
            updates: dict[str, object] = {"target_field": target_field}
            if transform is not None:
                updates["transform"] = transform
            mapping = mapping.model_copy(update=updates)
        updated.append(mapping)
    return config.model_copy(update={"field_mappings": updated})


class PipelineRunResult:
    """Outcome of a full insurer pipeline run."""

    def __init__(
        self,
        *,
        contract_pass_rate: float,
        survival_rate: float,
        overall_status: str,
        generation_syntax_valid: bool,
    ) -> None:
        self.contract_pass_rate = contract_pass_rate
        self.survival_rate = survival_rate
        self.overall_status = overall_status
        self.generation_syntax_valid = generation_syntax_valid


async def run_insurer_pipeline(
    *,
    sample_path: Path,
    client_name: str,
    source_format: str,
    semantic_matcher: SemanticMatcher,
    mock_field_analyzer: object,
    tmp_knowledge_base: object,
    gen_dir: Path,
    reports_dir: Path,
    expected_count: int,
    contract_threshold: float,
    survival_threshold: float,
    data_dictionary: str | None = None,
    legacy_bundle: LegacyBundle | None = None,
    extra_discover_path: Path | None = None,
) -> PipelineRunResult:
    """Discover, map, generate, and validate an insurer sample."""
    raw = sample_path.read_bytes()
    discovery = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
    profile = await discovery.discover(
        raw,
        client_name,
        data_dictionary=data_dictionary,
    )
    assert profile.source_format == source_format, (
        f"discovery: expected format {source_format}, got {profile.source_format}"
    )

    if extra_discover_path is not None:
        api_profile = await discovery.discover(extra_discover_path.read_bytes(), client_name)
        api_names = {f.source_name for f in api_profile.fields}
        sample_names = {f.source_name for f in profile.fields}
        overlap = api_names & sample_names
        assert overlap, f"discovery: OpenAPI/sample field overlap empty ({client_name})"

    mapping_engine = MappingEngine(
        LLMClient(api_key="test"),
        tmp_knowledge_base,  # type: ignore[arg-type]
        semantic_matcher=semantic_matcher,
    )
    config = await mapping_engine.map(profile)
    config.field_mappings = _filter_claim_mappings(config.field_mappings)
    config = _apply_transform_overrides(config, semantic_matcher)
    mapped = {m.source_field for m in config.field_mappings}
    assert len(mapped) >= min(8, len(profile.fields)), (
        f"mapping: too few claim-level mappings ({len(mapped)} from {len(profile.fields)} fields)"
    )

    gen_result = GeneratorEngine().generate(config, gen_dir)
    assert gen_result.syntax_valid, "generation: syntax_valid is False"

    registry = AdapterRegistry(registry_path=gen_dir / "registry.json")
    registry.register(gen_result, config)
    adapter_cls = registry.get_adapter_class(config.client_name)
    adapter = adapter_cls()

    contract_runner = ContractTestRunner()
    roundtrip = RoundTripValidator()

    if legacy_bundle is not None:
        claim_rows = [
            {k: v for k, v in row.items() if not str(k).startswith("_")}
            for row in legacy_bundle.joined_records
        ]
        contract_result = contract_runner.run_records(adapter, claim_rows)
        roundtrip_result = roundtrip.validate_records(adapter, claim_rows)
    else:
        contract_result = contract_runner.run(adapter, raw, expected_count=expected_count)
        roundtrip_result = roundtrip.validate(adapter, raw)

    assert contract_result.pass_rate >= contract_threshold, (
        f"contract: pass_rate {contract_result.pass_rate:.3f} < {contract_threshold}"
    )
    assert roundtrip_result.field_survival_rate >= survival_threshold, (
        f"roundtrip: survival {roundtrip_result.field_survival_rate:.3f} < {survival_threshold}"
    )

    reporter = TestReporter()
    report = reporter.generate_report(contract_result, roundtrip_result)
    assert report.overall_status in ("pass", "warn"), (
        f"reporter: overall_status {report.overall_status}"
    )

    report_path = reports_dir / f"{client_name}_report"
    reporter.save_report(report, report_path)

    for path in gen_dir.glob("*.py"):
        path.unlink(missing_ok=True)
    reg = gen_dir / "registry.json"
    if reg.exists():
        reg.unlink()

    return PipelineRunResult(
        contract_pass_rate=contract_result.pass_rate,
        survival_rate=roundtrip_result.field_survival_rate,
        overall_status=report.overall_status,
        generation_syntax_valid=gen_result.syntax_valid,
    )
