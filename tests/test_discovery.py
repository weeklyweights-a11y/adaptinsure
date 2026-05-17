"""Tests for discovery models, format detection, and engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.discovery.profile import ClientProfile, FieldInfo

UTC = timezone.utc


class TestFieldInfo:
    """FieldInfo model tests."""

    def test_field_info_creates_with_required_fields(self) -> None:
        """FieldInfo with all required fields creates successfully."""
        field = FieldInfo(
            source_name="lossDate",
            inferred_type="date",
            sample_values=["2024-01-01"],
            nullable=False,
            confidence=0.8,
        )
        assert field.source_name == "lossDate"
        assert field.inferred_type == "date"

    def test_field_info_stores_sample_values(self) -> None:
        """FieldInfo stores sample_values list correctly."""
        field = FieldInfo(
            source_name="status",
            inferred_type="string",
            sample_values=["open", "closed", "open"],
        )
        assert field.sample_values == ["open", "closed", "open"]

    def test_field_info_confidence_below_zero_raises(self) -> None:
        """Confidence below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            FieldInfo(source_name="x", inferred_type="string", confidence=-0.1)

    def test_field_info_confidence_above_one_raises(self) -> None:
        """Confidence above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            FieldInfo(source_name="x", inferred_type="string", confidence=1.1)

    def test_field_info_caps_sample_values_at_five(self) -> None:
        """Sample values are capped at five entries."""
        field = FieldInfo(
            source_name="x",
            inferred_type="string",
            sample_values=["1", "2", "3", "4", "5", "6", "7"],
        )
        assert len(field.sample_values) == 5

    def test_field_info_invalid_inferred_type_raises(self) -> None:
        """Invalid inferred_type raises ValidationError."""
        with pytest.raises(ValidationError):
            FieldInfo(source_name="x", inferred_type="blob")  # type: ignore[arg-type]


class TestClientProfile:
    """ClientProfile model tests."""

    def test_client_profile_creates_with_fields(self) -> None:
        """ClientProfile with valid fields list creates successfully."""
        fields = [
            FieldInfo(source_name="claimId", inferred_type="string"),
            FieldInfo(source_name="lossDate", inferred_type="date"),
        ]
        profile = ClientProfile(
            client_name="test-carrier",
            source_format="json",
            detected_encoding="utf-8",
            total_records_sampled=1,
            total_fields_detected=2,
            fields=fields,
            created_at=datetime.now(UTC),
        )
        assert len(profile.fields) == 2

    def test_client_profile_empty_fields_allowed(self) -> None:
        """ClientProfile with empty fields list creates successfully."""
        profile = ClientProfile(
            client_name="empty",
            source_format="unknown",
            detected_encoding="utf-8",
            total_records_sampled=0,
            total_fields_detected=0,
            fields=[],
            created_at=datetime.now(UTC),
        )
        assert profile.fields == []

    def test_client_profile_field_count_mismatch_raises(self) -> None:
        """total_fields_detected must match len(fields)."""
        with pytest.raises(ValidationError):
            ClientProfile(
                client_name="bad",
                source_format="json",
                detected_encoding="utf-8",
                total_records_sampled=0,
                total_fields_detected=5,
                fields=[],
                created_at=datetime.now(UTC),
            )
