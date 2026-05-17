"""Tests for discovery format parsers."""

from __future__ import annotations

import json

import pytest

from src.discovery.merge import merge_dictionary_fields
from src.discovery.parsers.csv_parser import parse_csv
from src.discovery.parsers.doc_parser import parse_data_dictionary
from src.discovery.parsers.json_parser import is_openapi_document, parse_json, parse_openapi_spec
from src.discovery.parsers.xml_parser import detect_acord_version, parse_xml
from src.discovery.profile import FieldInfo


class TestJsonParser:
    """JSON parser tests."""

    def test_single_object_produces_fields(self) -> None:
        """Single JSON object produces FieldInfo per key."""
        result = parse_json('{"claimId": "C1", "lossDate": "2024-01-01"}')
        names = {f.source_name for f in result.fields}
        assert "claimId" in names
        assert "lossDate" in names

    def test_array_samples_multiple_records(self) -> None:
        """JSON array collects samples from multiple records."""
        raw = json.dumps(
            [
                {"status": "open"},
                {"status": "closed"},
            ]
        )
        result = parse_json(raw)
        status = next(f for f in result.fields if f.source_name == "status")
        assert "open" in status.sample_values
        assert "closed" in status.sample_values
        assert result.record_count == 2

    def test_nested_object_nesting_path(self) -> None:
        """Nested objects produce nesting_path."""
        result = parse_json('{"address": {"city": "Austin"}}')
        city = next(f for f in result.fields if f.source_name == "city")
        assert city.nesting_path == "address.city"

    def test_nested_array_nesting_path(self) -> None:
        """Array of objects produces nesting_path with []."""
        raw = '{"exposures": [{"amount": 100}, {"amount": 200}]}'
        result = parse_json(raw)
        amount = next(f for f in result.fields if f.source_name == "amount")
        assert amount.nesting_path is not None
        assert "[]" in amount.nesting_path

    def test_integer_inferred(self) -> None:
        """Integer values inferred as integer."""
        result = parse_json('{"count": 3}')
        field = next(f for f in result.fields if f.source_name == "count")
        assert field.inferred_type == "integer"

    def test_float_inferred_as_decimal(self) -> None:
        """Float values inferred as decimal."""
        result = parse_json('{"amount": 12.5}')
        field = next(f for f in result.fields if f.source_name == "amount")
        assert field.inferred_type == "decimal"

    def test_boolean_inferred(self) -> None:
        """Boolean values inferred as boolean."""
        result = parse_json('{"active": true}')
        field = next(f for f in result.fields if f.source_name == "active")
        assert field.inferred_type == "boolean"

    def test_nullable_detected(self) -> None:
        """Null values mark field nullable."""
        result = parse_json('[{"x": null}, {"x": "a"}]')
        field = next(f for f in result.fields if f.source_name == "x")
        assert field.nullable is True

    def test_iso_date_format_pattern(self) -> None:
        """ISO date strings get format_pattern."""
        result = parse_json('{"lossDate": "2024-01-15"}')
        field = next(f for f in result.fields if f.source_name == "lossDate")
        assert field.format_pattern == "YYYY-MM-DD"

    def test_mixed_types_becomes_string(self) -> None:
        """Mixed types across records infer string."""
        raw = json.dumps([{"x": 1}, {"x": "text"}])
        result = parse_json(raw)
        field = next(f for f in result.fields if f.source_name == "x")
        assert field.inferred_type == "string"


class TestOpenApiParser:
    """OpenAPI parser tests."""

    def test_simple_schema_properties(self) -> None:
        """Simple schema yields FieldInfo per property."""
        spec = json.dumps(
            {
                "openapi": "3.0.0",
                "components": {
                    "schemas": {
                        "Claim": {
                            "properties": {
                                "claimId": {"type": "string", "description": "Claim ID"},
                            }
                        }
                    }
                },
            }
        )
        result = parse_openapi_spec(spec)
        assert any(f.source_name == "claimId" for f in result.fields)

    def test_description_populated(self) -> None:
        """OpenAPI description maps to FieldInfo.description."""
        spec = json.dumps(
            {
                "openapi": "3.0.0",
                "components": {
                    "schemas": {
                        "Claim": {
                            "properties": {
                                "lossDate": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "Date of loss",
                                }
                            }
                        }
                    }
                },
            }
        )
        result = parse_openapi_spec(spec)
        field = next(f for f in result.fields if f.source_name == "lossDate")
        assert field.description == "Date of loss"
        assert field.format_pattern == "date"

    def test_ref_resolves_one_level(self) -> None:
        """One-level $ref resolves nested properties."""
        spec = json.dumps(
            {
                "openapi": "3.0.0",
                "components": {
                    "schemas": {
                        "Address": {
                            "properties": {"city": {"type": "string"}},
                        },
                        "Claim": {
                            "properties": {
                                "address": {"$ref": "#/components/schemas/Address"},
                            }
                        },
                    }
                },
            }
        )
        result = parse_openapi_spec(spec)
        assert any(f.source_name == "address" for f in result.fields)

    def test_is_openapi_document(self) -> None:
        """is_openapi_document detects openapi root key."""
        assert is_openapi_document({"openapi": "3.0.0"}) is True
        assert is_openapi_document({"claims": []}) is False


class TestXmlParser:
    """XML parser tests."""

    def test_simple_elements(self) -> None:
        """Simple XML produces fields."""
        result = parse_xml("<claim><id>1</id><status>open</status></claim>")
        names = {f.source_name for f in result.fields}
        assert "id" in names
        assert "status" in names

    def test_attributes_as_fields(self) -> None:
        """Attributes produce element@attr source names."""
        result = parse_xml('<claim id="99"><status>open</status></claim>')
        assert any("@" in f.source_name for f in result.fields)

    def test_namespace_stripped_source_name(self) -> None:
        """Namespace prefix stripped from source_name."""
        xml = (
            '<ns:claim xmlns:ns="http://example.com">'
            "<ns:id>1</ns:id></ns:claim>"
        )
        result = parse_xml(xml)
        assert all("ns:" not in f.source_name for f in result.fields)

    def test_empty_element_nullable(self) -> None:
        """Empty elements are nullable."""
        result = parse_xml("<claim><empty/></claim>")
        empty = next((f for f in result.fields if f.source_name == "empty"), None)
        assert empty is not None
        assert empty.nullable is True


class TestAcordDetection:
    """ACORD version detection tests."""

    def test_acord_namespace_returns_version(self) -> None:
        """ACORD XML with Version attribute returns version."""
        xml = (
            '<?xml version="1.0"?>'
            '<ACORD xmlns="http://www.ACORD.org/standards/PC_Surety/ACORD1/xml/" '
            'Version="1.0"><Claim/></ACORD>'
        )
        assert detect_acord_version(xml) == "1.0"

    def test_non_acord_returns_none(self) -> None:
        """Non-ACORD XML returns None."""
        assert detect_acord_version("<claims><claim/></claims>") is None

    def test_acord_without_version_returns_unknown(self) -> None:
        """ACORD without Version returns unknown."""
        xml = (
            '<Root xmlns="http://www.ACORD.org/standards/PC_Surety/ACORD1/xml/">'
            "<Claim/></Root>"
        )
        assert detect_acord_version(xml) == "unknown"


class TestCsvParser:
    """CSV parser tests."""

    def test_comma_delimited(self) -> None:
        """Comma CSV parses headers."""
        result = parse_csv("id,name\n1,John\n2,Jane\n")
        assert any(f.source_name == "name" for f in result.fields)
        assert result.record_count == 2

    def test_pipe_delimited(self) -> None:
        """Pipe delimiter detected."""
        result = parse_csv("id|name\n1|John\n")
        assert any(f.source_name == "name" for f in result.fields)

    def test_tab_delimited(self) -> None:
        """Tab delimiter detected."""
        result = parse_csv("id\tname\n1\tJohn\n")
        assert any(f.source_name == "name" for f in result.fields)

    def test_semicolon_delimited(self) -> None:
        """Semicolon delimiter detected."""
        result = parse_csv("id;name\n1;John\n")
        assert any(f.source_name == "name" for f in result.fields)

    def test_no_header_synthetic_columns(self) -> None:
        """Missing header generates col_N names."""
        result = parse_csv("1,John\n2,Jane\n")
        assert any(f.source_name.startswith("col_") for f in result.fields)

    def test_integer_column(self) -> None:
        """Integer column inferred."""
        result = parse_csv("count\n3\n5\n")
        field = next(f for f in result.fields if f.source_name == "count")
        assert field.inferred_type == "integer"

    def test_decimal_column(self) -> None:
        """Decimal column inferred."""
        result = parse_csv("amount\n12.5\n3.1\n")
        field = next(f for f in result.fields if f.source_name == "amount")
        assert field.inferred_type == "decimal"

    def test_date_column_iso(self) -> None:
        """YYYY-MM-DD date column."""
        result = parse_csv("loss_date\n2024-01-15\n")
        field = next(f for f in result.fields if f.source_name == "loss_date")
        assert field.inferred_type == "date"

    def test_packed_date(self) -> None:
        """Packed YYYYMMDD detected."""
        result = parse_csv("loss_date\n20240115\n")
        field = next(f for f in result.fields if f.source_name == "loss_date")
        assert field.format_pattern == "YYYYMMDD packed"

    def test_boolean_column(self) -> None:
        """Boolean column inferred."""
        result = parse_csv("flag\ntrue\nfalse\n")
        field = next(f for f in result.fields if f.source_name == "flag")
        assert field.inferred_type == "boolean"

    def test_nullable_column(self) -> None:
        """Empty cells mark nullable."""
        result = parse_csv("a,b\n1,\n3,4\n")
        field = next(f for f in result.fields if f.source_name == "b")
        assert field.nullable is True

    def test_currency_pattern(self) -> None:
        """Currency values get format pattern."""
        result = parse_csv("amt\n$1,234.56\n")
        field = next(f for f in result.fields if f.source_name == "amt")
        assert field.format_pattern == "$#,###.##"


class TestDocParser:
    """Data dictionary parser tests."""

    def test_markdown_table(self) -> None:
        """Markdown table parsed."""
        doc = "| Field | Type | Description |\n| --- | --- | --- |\n| CLM_ID | string | Claim ID |"
        fields = parse_data_dictionary(doc)
        assert any(f.source_name == "CLM_ID" for f in fields)
        clm = next(f for f in fields if f.source_name == "CLM_ID")
        assert clm.description == "Claim ID"

    def test_key_value_format(self) -> None:
        """Key-value lines parsed."""
        fields = parse_data_dictionary("LOSS_DATE: Date of loss")
        assert fields[0].source_name == "LOSS_DATE"
        assert fields[0].description == "Date of loss"

    def test_malformed_returns_empty(self) -> None:
        """Malformed input returns empty list."""
        assert parse_data_dictionary("   ") == []


class TestMergeDictionary:
    """Dictionary merge tests."""

    def test_merge_enriches_description(self) -> None:
        """Merge updates description from dictionary."""
        parsed = [FieldInfo(source_name="lossDate", inferred_type="string")]
        doc = [
            FieldInfo(
                source_name="lossDate",
                inferred_type="date",
                description="Date of loss",
            )
        ]
        merged = merge_dictionary_fields(parsed, doc)
        assert merged[0].description == "Date of loss"
        assert merged[0].inferred_type == "date"

    def test_merge_appends_doc_only_field(self) -> None:
        """Doc-only fields are appended."""
        parsed = [FieldInfo(source_name="a", inferred_type="string")]
        doc = [FieldInfo(source_name="extra_field", inferred_type="unknown", description="Extra")]
        merged = merge_dictionary_fields(parsed, doc)
        assert len(merged) == 2
        assert any(f.source_name == "extra_field" for f in merged)
