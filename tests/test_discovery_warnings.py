"""Tests for discovery warning helpers."""

from __future__ import annotations

from src.discovery.profile import FieldInfo
from src.discovery.warnings import build_discovery_warnings, collect_nested_structures


class TestBuildDiscoveryWarnings:
    """build_discovery_warnings tests."""

    def test_no_sample_values_warning(self) -> None:
        """Fields without samples produce a warning."""
        fields = [
            FieldInfo(source_name="a", inferred_type="string", sample_values=[]),
            FieldInfo(source_name="b", inferred_type="string", sample_values=[]),
        ]
        warnings = build_discovery_warnings(fields)
        assert any("no sample values" in w for w in warnings)

    def test_mixed_date_formats_warning(self) -> None:
        """Mixed date separators produce a warning."""
        fields = [
            FieldInfo(
                source_name="lossDate",
                inferred_type="string",
                sample_values=["2024-01-01", "01/15/2024"],
            ),
        ]
        warnings = build_discovery_warnings(fields)
        assert any("mixed date formats" in w for w in warnings)


class TestCollectNestedStructures:
    """collect_nested_structures tests."""

    def test_collects_array_segments(self) -> None:
        """Paths with [] contribute nested structure names."""
        fields = [
            FieldInfo(
                source_name="amount",
                inferred_type="decimal",
                nesting_path="exposures[].amount",
            ),
        ]
        names = collect_nested_structures(fields)
        assert "exposures" in names
