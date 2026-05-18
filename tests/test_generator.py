"""Tests for the Adapter Code Generator."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from jinja2 import Environment, FileSystemLoader

from src.generator.context_builder import STRPTIME_FORMATS, build_template_context
from src.generator.engine import GeneratorEngine
from src.generator.name_utils import sanitize_client_name
from src.generator.registry import AdapterRegistry
from src.generator.schema_introspector import SchemaIntrospector
from src.mapping.config import (
    ConfidenceSummary,
    FieldMapping,
    FieldTransform,
    GapInfo,
    GapType,
    MappingConfig,
    MatchType,
    TransformType,
)
from src.schema.enums import ClaimStatus

_TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "generator" / "templates"


def _render_partial(template_name: str, **context: object) -> str:
    """Render a transform partial wrapped in a minimal class for ast.parse."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    body = env.get_template(template_name).render(**context)
    source = (
        "from datetime import datetime, timezone\n"
        "from decimal import Decimal\n"
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "class _Stub:\n"
        f"{body}\n"
    )
    return source


def _render_adapter(context: dict[object]) -> str:
    """Render full adapter template."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("adapter_class.py.j2").render(**context)


class TestSchemaIntrospector:
    """SchemaIntrospector tests (spec Step 1)."""

    def test_get_all_fields_includes_claim_paths(self) -> None:
        fields = SchemaIntrospector().get_all_fields()
        assert "claim.claim_id" in fields
        assert "claim.loss_date" in fields
        assert "claim.status" in fields

    def test_get_all_fields_includes_nested_address(self) -> None:
        fields = SchemaIntrospector().get_all_fields()
        assert "claim.loss_location.city" in fields
        assert "claim.loss_location.state" in fields

    def test_get_all_fields_includes_exposure(self) -> None:
        fields = SchemaIntrospector().get_all_fields()
        assert "exposure.exposure_id" in fields
        assert "exposure.reserved_amount" in fields

    def test_get_all_fields_includes_claimant_and_transaction(self) -> None:
        fields = SchemaIntrospector().get_all_fields()
        assert "claimant.first_name" in fields
        assert "transaction.amount" in fields

    def test_get_all_fields_includes_policy_snapshot(self) -> None:
        fields = SchemaIntrospector().get_all_fields()
        assert "policy_snapshot.policy_number" in fields

    def test_get_required_fields_claim_id_required(self) -> None:
        required = SchemaIntrospector().get_required_fields()
        assert "claim.claim_id" in required
        assert "claim.catastrophe_code" not in required

    def test_field_spec_status_is_enum(self) -> None:
        spec = SchemaIntrospector().get_all_fields()["claim.status"]
        assert spec.is_enum is True
        assert set(spec.enum_values or []) == {m.value for m in ClaimStatus}

    def test_field_spec_loss_date_datetime(self) -> None:
        spec = SchemaIntrospector().get_all_fields()["claim.loss_date"]
        assert spec.python_type == "datetime"

    def test_field_spec_total_paid_decimal(self) -> None:
        spec = SchemaIntrospector().get_all_fields()["claim.total_paid"]
        assert spec.python_type == "Decimal"

    def test_field_spec_exposures_is_list(self) -> None:
        spec = SchemaIntrospector().get_all_fields()["claim.exposures"]
        assert spec.is_list is True

    def test_field_count_sanity(self) -> None:
        count = len(SchemaIntrospector().get_all_fields())
        assert 40 <= count <= 90

    def test_get_entity_names(self) -> None:
        names = SchemaIntrospector().get_entity_names()
        assert names == [
            "claim",
            "exposure",
            "claimant",
            "transaction",
            "policy_snapshot",
        ]


class TestTransformTemplates:
    """Transform partial template tests (spec Step 3)."""

    def test_date_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/date_transform.py.j2",
            method_name="_transform_date_yyyy_mm_dd",
            strptime_format=STRPTIME_FORMATS["YYYY-MM-DD"],
        )
        ast.parse(source)
        assert "_transform_date_yyyy_mm_dd" in source
        assert "%Y-%m-%d" in source

    def test_currency_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/currency_transform.py.j2",
            method_name="_transform_currency",
        )
        ast.parse(source)
        assert "_transform_currency" in source
        assert "Decimal" in source

    def test_boolean_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/boolean_transform.py.j2",
            method_name="_transform_boolean",
            true_values=["true", "yes"],
            false_values=["false", "no"],
        )
        ast.parse(source)
        assert "true_values" in source or '"true"' in source

    def test_enum_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/enum_transform.py.j2",
            method_name="_transform_enum_claimstatus",
            enum_map={"OPN": "open"},
            target_enum_values=["open", "closed"],
        )
        ast.parse(source)
        assert "_transform_enum_claimstatus" in source

    def test_type_cast_transform_renders_decimal(self) -> None:
        source = _render_partial(
            "transforms/type_cast_transform.py.j2",
            method_name="_transform_type_cast_decimal",
            target_type="Decimal",
            return_annotation="Decimal",
        )
        ast.parse(source)

    def test_split_field_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/split_field_transform.py.j2",
            method_name="_transform_split_full_name",
            delimiter=",",
            maxsplit=1,
            targets=["claimant.first_name", "claimant.last_name"],
        )
        ast.parse(source)
        assert 'split(",")' in source or 'split(",",' in source

    def test_merge_fields_transform_renders_valid_python(self) -> None:
        source = _render_partial(
            "transforms/merge_fields_transform.py.j2",
            method_name="_transform_merge_loss_location",
            target_field="claim.loss_location",
            field_map={"street_1": "street", "city": "city"},
        )
        ast.parse(source)

    def test_transform_templates_handle_none(self) -> None:
        for template, ctx in [
            (
                "transforms/date_transform.py.j2",
                {
                    "method_name": "_transform_date_x",
                    "strptime_format": "%Y-%m-%d",
                },
            ),
            ("transforms/currency_transform.py.j2", {"method_name": "_transform_currency"}),
        ]:
            source = _render_partial(template, **ctx)
            assert "None" in source
            assert "logger.warning" in source


class TestAdapterTemplate:
    """Adapter class template tests (spec Step 2)."""

    def test_adapter_template_valid_python(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = _render_adapter(context)
        ast.parse(source)

    def test_adapter_template_class_name(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = _render_adapter(context)
        assert f"class {context['class_name']}(BaseAdapter)" in source

    def test_adapter_template_field_mappings(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = _render_adapter(context)
        assert '"lossDate": "claim.loss_date"' in source
        assert "FIELD_MAPPINGS" in source
        assert "TRANSFORMS" in source
        assert "parse_raw" in source
        assert "map_record" in source
        assert "validate_record" in source

    def test_adapter_template_header_timestamp(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = _render_adapter(context)
        assert "DO NOT EDIT" in source
        assert fixed_generation_timestamp.isoformat() in source

    def test_adapter_template_only_needed_transforms(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = _render_adapter(context)
        assert "_transform_date_" in source
        assert "_transform_currency" in source
        assert "_transform_boolean" in source
        assert source.count("def _transform_merge_") == 0


class TestTestAdapterTemplate:
    """Generated test file template tests (spec Step 4)."""

    def test_test_template_valid_python(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = env.get_template("test_adapter.py.j2").render(**context)
        ast.parse(source)

    def test_test_template_imports_adapter(
        self,
        test_mapping_config: MappingConfig,
        fixed_generation_timestamp: datetime,
    ) -> None:
        env = Environment(loader=FileSystemLoader(str(_TEMPLATES)))
        context = build_template_context(
            test_mapping_config,
            timestamp=fixed_generation_timestamp,
        )
        source = env.get_template("test_adapter.py.j2").render(**context)
        assert f"from {context['module_name']} import {context['class_name']}" in source
        assert "sample_raw_json" in source
        assert "test_parse_raw_returns_records" in source


class TestGeneratorEngine:
    """GeneratorEngine tests (spec Step 5)."""

    def test_generate_produces_two_files(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
        fixed_generation_timestamp: datetime,
    ) -> None:
        engine = GeneratorEngine()
        result = engine.generate(
            test_mapping_config,
            tmp_path,
            timestamp=fixed_generation_timestamp,
        )
        assert result.adapter_file.exists()
        assert result.test_file.exists()
        assert result.syntax_valid is True

    def test_generate_sanitized_class_name(self, tmp_path: Path) -> None:
        config = MappingConfig(
            client_name="Guidewire Carrier A",
            source_format="json",
            schema_version="1.0.0",
            field_mappings=[
                FieldMapping(
                    source_field="id",
                    target_field="claim.claim_id",
                    match_type=MatchType.DIRECT,
                    confidence=1.0,
                    reasoning="direct",
                ),
            ],
            transforms=[],
            gaps=[],
            confidence_summary=ConfidenceSummary(
                total_fields=1,
                mapped_fields=1,
                unmapped_fields=0,
                high_confidence_count=1,
                medium_confidence_count=0,
                low_confidence_count=0,
                average_confidence=1.0,
            ),
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        result = GeneratorEngine().generate(config, tmp_path)
        assert result.class_name == "GuidewireCarrierAAdapter"

    def test_sanitize_special_chars(self) -> None:
        class_name, _, _, _ = sanitize_client_name("carrier-#1")
        assert class_name == "Carrier1Adapter"

    def test_generate_warnings_requires_review(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
    ) -> None:
        config = test_mapping_config.model_copy(
            update={
                "confidence_summary": test_mapping_config.confidence_summary.model_copy(
                    update={"low_confidence_count": 1, "requires_review": True},
                ),
            },
        )
        result = GeneratorEngine().generate(config, tmp_path)
        assert any("review" in w.lower() for w in result.warnings)

    def test_generate_critical_gap_warning(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
    ) -> None:
        config = test_mapping_config.model_copy(
            update={
                "gaps": [
                    *test_mapping_config.gaps,
                    GapInfo(
                        field_name="claim.claim_id",
                        gap_type=GapType.MISSING_REQUIRED,
                        severity="critical",
                        description="missing",
                    ),
                ],
            },
        )
        result = GeneratorEngine().generate(config, tmp_path)
        assert any("Critical gap" in w for w in result.warnings)


class TestAdapterRegistry:
    """AdapterRegistry tests (spec Step 6)."""

    def test_register_and_list(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
        fixed_generation_timestamp: datetime,
    ) -> None:
        registry_path = tmp_path / "registry.json"
        registry = AdapterRegistry(registry_path=registry_path)
        result = GeneratorEngine().generate(
            test_mapping_config,
            tmp_path,
            timestamp=fixed_generation_timestamp,
        )
        registry.register(result, test_mapping_config)
        adapters = registry.list_adapters()
        assert len(adapters) == 1
        assert adapters[0].client_name == test_mapping_config.client_name

    def test_get_adapter_class_loads_and_caches(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
        fixed_generation_timestamp: datetime,
    ) -> None:
        registry = AdapterRegistry(registry_path=tmp_path / "registry.json")
        result = GeneratorEngine().generate(
            test_mapping_config,
            tmp_path,
            timestamp=fixed_generation_timestamp,
        )
        registry.register(result, test_mapping_config)
        cls1 = registry.get_adapter_class(test_mapping_config.client_name)
        with patch("importlib.util.spec_from_file_location") as mock_spec:
            cls2 = registry.get_adapter_class(test_mapping_config.client_name)
        assert cls1 is cls2
        mock_spec.assert_not_called()

    def test_get_adapter_class_unknown_raises(self, tmp_path: Path) -> None:
        registry = AdapterRegistry(registry_path=tmp_path / "registry.json")
        from src.exceptions import GenerationError
        from src.generator.codes import GEN_ADAPTER_NOT_FOUND

        with pytest.raises(GenerationError) as exc_info:
            registry.get_adapter_class("missing")
        assert exc_info.value.error_code == GEN_ADAPTER_NOT_FOUND

    def test_get_adapter_for_format(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
    ) -> None:
        registry = AdapterRegistry(registry_path=tmp_path / "registry.json")
        result = GeneratorEngine().generate(test_mapping_config, tmp_path)
        registry.register(result, test_mapping_config)
        matches = registry.get_adapter_for_format("json")
        assert len(matches) == 1
        assert registry.get_adapter_for_format("xml") == []

    def test_remove_adapter(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
    ) -> None:
        registry = AdapterRegistry(registry_path=tmp_path / "registry.json")
        result = GeneratorEngine().generate(test_mapping_config, tmp_path)
        registry.register(result, test_mapping_config)
        assert registry.remove(test_mapping_config.client_name) is True
        assert registry.remove("nope") is False
        assert registry.list_adapters() == []

    def test_registry_persists_json(
        self,
        test_mapping_config: MappingConfig,
        tmp_path: Path,
    ) -> None:
        registry_path = tmp_path / "registry.json"
        registry = AdapterRegistry(registry_path=registry_path)
        result = GeneratorEngine().generate(test_mapping_config, tmp_path)
        registry.register(result, test_mapping_config)
        reloaded = AdapterRegistry(registry_path=registry_path)
        assert len(reloaded.list_adapters()) == 1
