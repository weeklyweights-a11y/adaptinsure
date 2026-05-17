"""Tests for discovery models, format detection, and engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.discovery.parsers import detect_format
from src.discovery.profile import ClientProfile, FieldInfo
from src.exceptions import DiscoveryError

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


class TestDetectFormat:
    """Format detection tests."""

    def test_json_object_detected(self) -> None:
        """JSON object returns json."""
        assert detect_format('{"claim_id": "123"}') == "json"

    def test_json_array_detected(self) -> None:
        """JSON array returns json."""
        assert detect_format('[{"claim_id": "123"}]') == "json"

    def test_xml_with_declaration_detected(self) -> None:
        """XML with declaration returns xml."""
        assert detect_format('<?xml version="1.0"?><claims></claims>') == "xml"

    def test_xml_without_declaration_detected(self) -> None:
        """XML without declaration returns xml."""
        assert detect_format('<claims><claim id="1"/></claims>') == "xml"

    def test_csv_comma_detected(self) -> None:
        """Comma-delimited CSV returns csv."""
        assert detect_format("id,name,date\n1,John,2024-01-01\n") == "csv"

    def test_csv_pipe_detected(self) -> None:
        """Pipe-delimited data returns csv."""
        assert detect_format("id|name|date\n1|John|2024-01-01\n") == "csv"

    def test_empty_input_raises(self) -> None:
        """Empty input raises DiscoveryError."""
        with pytest.raises(DiscoveryError) as exc_info:
            detect_format("")
        assert exc_info.value.error_code == "DISC_EMPTY_INPUT"

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only input raises DiscoveryError."""
        with pytest.raises(DiscoveryError):
            detect_format("   \n\t  ")

    def test_binary_garbage_returns_unknown(self) -> None:
        """Non-structured text returns unknown."""
        assert detect_format("not a format at all really") == "unknown"

    def test_json_with_leading_whitespace(self) -> None:
        """JSON with leading whitespace still detected."""
        assert detect_format('  {"claim_id": "123"}') == "json"

    def test_fixed_width_heuristic(self) -> None:
        """Uniform line lengths return fixed_width."""
        raw = "ID  NAME    DATE      \n001 John    20240101  \n002 Jane    20240102  \n"
        assert detect_format(raw) == "fixed_width"


class TestDiscoveryEngine:
    """DiscoveryEngine integration tests (mocked analyzer)."""

    @pytest.mark.asyncio
    async def test_json_produces_client_profile(
        self,
        sample_json_claims: str,
        mock_field_analyzer: object,
    ) -> None:
        """JSON input produces valid ClientProfile."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(sample_json_claims, "gw-carrier")
        assert profile.source_format == "json"
        assert profile.total_fields_detected == len(profile.fields)
        assert any(f.insurance_annotation for f in profile.fields)

    @pytest.mark.asyncio
    async def test_xml_produces_client_profile(
        self,
        sample_xml_claims: str,
        mock_field_analyzer: object,
    ) -> None:
        """XML input produces valid ClientProfile."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(sample_xml_claims, "acord-carrier")
        assert profile.source_format == "xml"
        assert any("ACORD" in note for note in profile.notes)

    @pytest.mark.asyncio
    async def test_csv_produces_client_profile(
        self,
        sample_csv_claims: str,
        mock_field_analyzer: object,
    ) -> None:
        """CSV input produces valid ClientProfile."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(sample_csv_claims, "legacy-carrier")
        assert profile.source_format == "csv"
        assert profile.total_records_sampled == 4

    @pytest.mark.asyncio
    async def test_dictionary_merge(
        self,
        sample_json_claims: str,
        sample_data_dictionary: str,
        mock_field_analyzer: object,
    ) -> None:
        """Data dictionary merge enriches and appends fields."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(
            sample_json_claims,
            "gw-carrier",
            data_dictionary=sample_data_dictionary,
        )
        assert any(f.source_name == "extraDocField" for f in profile.fields)

    @pytest.mark.asyncio
    async def test_empty_input_raises(self, mock_field_analyzer: object) -> None:
        """Empty input raises DiscoveryError."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        with pytest.raises(DiscoveryError) as exc_info:
            await engine.discover("", "client")
        assert exc_info.value.error_code == "DISC_EMPTY_INPUT"

    @pytest.mark.asyncio
    async def test_unknown_format_raises(self, mock_field_analyzer: object) -> None:
        """Unknown format raises DiscoveryError."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        with pytest.raises(DiscoveryError) as exc_info:
            await engine.discover("plain text only", "client")
        assert exc_info.value.error_code == "DISC_UNSUPPORTED_FORMAT"

    @pytest.mark.asyncio
    async def test_fixed_width_raises(self, mock_field_analyzer: object) -> None:
        """Fixed-width format raises DiscoveryError."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        raw = "ID  NAME    DATE      \n001 John    20240101  \n002 Jane    20240102  \n"
        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        with pytest.raises(DiscoveryError) as exc_info:
            await engine.discover(raw, "client")
        assert exc_info.value.error_code == "DISC_UNSUPPORTED_FORMAT"

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self, mock_field_analyzer: object) -> None:
        """Invalid JSON-like input raises DiscoveryError (unsupported or parse failed)."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        with pytest.raises(DiscoveryError) as exc_info:
            await engine.discover("{not json", "client")
        assert exc_info.value.error_code in ("DISC_PARSE_FAILED", "DISC_UNSUPPORTED_FORMAT")

    @pytest.mark.asyncio
    async def test_malformed_xml_raises(self, mock_field_analyzer: object) -> None:
        """Malformed XML raises DISC_PARSE_FAILED."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        with pytest.raises(DiscoveryError) as exc_info:
            await engine.discover("<unclosed>", "client")
        assert exc_info.value.error_code == "DISC_PARSE_FAILED"

    @pytest.mark.asyncio
    async def test_json_notes_camel_case(
        self,
        sample_json_claims: str,
        mock_field_analyzer: object,
    ) -> None:
        """JSON profile notes mention camelCase when applicable."""
        from src.discovery.engine import DiscoveryEngine
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(sample_json_claims, "gw-carrier")
        assert any("camelCase" in note for note in profile.notes)

    @pytest.mark.asyncio
    async def test_client_profile_json_round_trip(
        self,
        sample_json_claims: str,
        mock_field_analyzer: object,
    ) -> None:
        """ClientProfile serializes to JSON and validates on load."""
        from src.discovery.engine import DiscoveryEngine
        from src.discovery.profile import ClientProfile
        from src.llm.client import LLMClient

        engine = DiscoveryEngine(LLMClient(api_key="test"), field_analyzer=mock_field_analyzer)
        profile = await engine.discover(sample_json_claims, "gw-carrier")
        payload = profile.model_dump_json()
        restored = ClientProfile.model_validate_json(payload)
        assert restored.client_name == profile.client_name
        assert len(restored.fields) == len(profile.fields)
