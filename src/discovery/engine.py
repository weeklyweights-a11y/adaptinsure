"""Discovery Engine orchestrator."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import yaml

from src.discovery.analyzer import InsuranceFieldAnalyzer
from src.discovery.codes import (
    DISC_EMPTY_INPUT,
    DISC_PARSE_FAILED,
    DISC_PROFILE_BUILD_FAILED,
    DISC_UNSUPPORTED_FORMAT,
)
from src.discovery.merge import merge_dictionary_fields
from src.discovery.parsers import decode_raw_input, detect_format
from src.discovery.parsers.csv_parser import parse_csv
from src.discovery.parsers.doc_parser import parse_data_dictionary
from src.discovery.parsers.json_parser import (
    is_openapi_document,
    parse_json,
    parse_openapi_spec,
)
from src.discovery.parsers.types import ParserResult
from src.discovery.parsers.xml_parser import parse_xml
from src.discovery.profile import ClientProfile, FieldInfo
from src.discovery.warnings import build_discovery_warnings, collect_nested_structures
from src.exceptions import ConfigError, DiscoveryError, LLMError
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

class DiscoveryEngine:
    """Main entry point: raw insurer data to ClientProfile."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        field_analyzer: InsuranceFieldAnalyzer | None = None,
    ) -> None:
        """Initialize with LLM client and optional analyzer override for tests."""
        self._llm_client = llm_client
        self._analyzer = field_analyzer or InsuranceFieldAnalyzer(llm_client)

    async def discover(
        self,
        raw_input: str | bytes,
        client_name: str,
        data_dictionary: str | None = None,
    ) -> ClientProfile:
        """Discover client data format and produce a ClientProfile."""
        encoding = "utf-8"
        text: str
        step_start = time.perf_counter()

        try:
            if isinstance(raw_input, bytes):
                text, encoding = decode_raw_input(raw_input)
            else:
                text = raw_input
                if not text.strip():
                    raise DiscoveryError(
                        DISC_EMPTY_INPUT,
                        "Input is empty",
                        details={"step": "discover"},
                    )
        except DiscoveryError:
            raise
        except Exception as exc:
            raise DiscoveryError(
                DISC_EMPTY_INPUT,
                f"Failed to decode input: {exc}",
                details={"step": "decode"},
            ) from exc
        logger.info("decode step completed in %.1f ms", (time.perf_counter() - step_start) * 1000)

        step_start = time.perf_counter()
        try:
            source_format = detect_format(text)
        except DiscoveryError:
            raise
        logger.info(
            "detect_format=%s in %.1f ms",
            source_format,
            (time.perf_counter() - step_start) * 1000,
        )

        if source_format in {"unknown", "fixed_width"}:
            raise DiscoveryError(
                DISC_UNSUPPORTED_FORMAT,
                f"Unsupported format: {source_format}",
                details={"format": source_format, "step": "route"},
            )

        step_start = time.perf_counter()
        try:
            parser_result, notes = self._parse_input(text, source_format)
        except DiscoveryError:
            raise
        except (json.JSONDecodeError, yaml.YAMLError, ET.ParseError, ValueError) as exc:
            raise DiscoveryError(
                DISC_PARSE_FAILED,
                f"Failed to parse {source_format} input: {exc}",
                details={"step": "parse", "format": source_format, "cause": str(exc)},
            ) from exc
        logger.info("parse step completed in %.1f ms", (time.perf_counter() - step_start) * 1000)

        fields = parser_result.fields
        notes = list(notes) + list(parser_result.parser_notes)

        if data_dictionary:
            doc_fields = parse_data_dictionary(data_dictionary)
            fields = merge_dictionary_fields(fields, doc_fields)
            notes.append("Data dictionary merged into field descriptions")

        step_start = time.perf_counter()
        try:
            fields = await self._analyzer.annotate_fields(fields, source_format, notes)
        except (ConfigError, LLMError):
            raise
        logger.info("annotate step completed in %.1f ms", (time.perf_counter() - step_start) * 1000)

        warnings = build_discovery_warnings(fields)
        nested = collect_nested_structures(fields)
        notes.extend(self._format_notes(source_format, fields))

        try:
            profile = ClientProfile(
                client_name=client_name,
                source_format=source_format,  # type: ignore[arg-type]
                detected_encoding=encoding,
                total_records_sampled=parser_result.record_count,
                total_fields_detected=len(fields),
                fields=fields,
                nested_structures=nested,
                notes=notes,
                raw_sample=parser_result.raw_sample,
                created_at=datetime.now(UTC),
                warnings=warnings,
            )
        except ValueError as exc:
            raise DiscoveryError(
                DISC_PROFILE_BUILD_FAILED,
                f"Failed to build ClientProfile: {exc}",
                details={"step": "build_profile"},
            ) from exc

        return profile

    def _parse_input(self, text: str, source_format: str) -> tuple[ParserResult, list[str]]:
        """Route to the correct parser for the detected format."""
        notes: list[str] = []
        if source_format == "json":
            data = json.loads(text)
            if isinstance(data, dict) and is_openapi_document(data):
                return parse_openapi_spec(text), notes
            return parse_json(text), notes
        if source_format == "xml":
            return parse_xml(text), notes
        if source_format == "csv":
            return parse_csv(text), notes
        raise DiscoveryError(
            DISC_UNSUPPORTED_FORMAT,
            f"No parser for format: {source_format}",
            details={"format": source_format},
        )

    def _format_notes(self, source_format: str, fields: list[FieldInfo]) -> list[str]:
        """Add format-specific observation notes."""
        extra: list[str] = []
        if source_format == "json":
            camel = [
                f
                for f in fields
                if f.source_name[:1].islower() and any(c.isupper() for c in f.source_name)
            ]
            if camel:
                extra.append("Guidewire-style camelCase naming detected")
        return extra
