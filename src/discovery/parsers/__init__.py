"""Format detection and parser package for the Discovery Engine."""

from __future__ import annotations

import csv
import json
from typing import Final

import chardet

from src.discovery.codes import (
    DISC_EMPTY_INPUT,
    DISC_UNREADABLE_INPUT,
)
from src.discovery.parsers.types import ParserResult
from src.exceptions import DiscoveryError

__all__ = [
    "ParserResult",
    "decode_raw_input",
    "detect_format",
]

_ENCODING_FALLBACKS: Final[tuple[str, ...]] = ("utf-8", "latin-1", "cp1252")
_SNIFF_SAMPLE_SIZE: Final[int] = 8192
_FIXED_WIDTH_MIN_LINES: Final[int] = 3
_FIXED_WIDTH_TOLERANCE: Final[int] = 2


def decode_raw_input(raw: bytes) -> tuple[str, str]:
    """Decode bytes to str using chardet with fallbacks.

    Returns:
        Tuple of (decoded text, encoding name).
    """
    if not raw:
        raise DiscoveryError(
            DISC_EMPTY_INPUT,
            "Input is empty",
            details={"step": "decode"},
        )
    detected = chardet.detect(raw)
    encoding = detected.get("encoding") if detected else None
    if encoding:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            pass
    for fallback in _ENCODING_FALLBACKS:
        try:
            return raw.decode(fallback), fallback
        except UnicodeDecodeError:
            continue
    raise DiscoveryError(
        DISC_UNREADABLE_INPUT,
        "Could not decode input bytes",
        details={"step": "decode"},
    )


def detect_format(raw_input: str | bytes) -> str:
    """Detect data format from raw input.

    Returns one of: json, xml, csv, fixed_width, unknown.
    """
    if isinstance(raw_input, bytes):
        text, _ = decode_raw_input(raw_input)
    else:
        text = raw_input

    stripped = text.strip()
    if not stripped:
        raise DiscoveryError(
            DISC_EMPTY_INPUT,
            "Input is empty or whitespace only",
            details={"step": "detect_format"},
        )

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return "json"
        except json.JSONDecodeError:
            pass

    if stripped.startswith("<") or stripped.startswith("<?xml"):
        return "xml"

    sample = stripped[:_SNIFF_SAMPLE_SIZE]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        if dialect.delimiter:
            return "csv"
    except csv.Error:
        pass

    if _looks_like_fixed_width(stripped):
        return "fixed_width"

    return "unknown"


def _looks_like_fixed_width(text: str) -> bool:
    """Return True if lines have consistent width suggesting fixed-width data."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < _FIXED_WIDTH_MIN_LINES:
        return False
    lengths = [len(line.rstrip("\r")) for line in lines]
    if len(set(lengths)) == 1:
        return True
    min_len = min(lengths)
    max_len = max(lengths)
    return max_len - min_len <= _FIXED_WIDTH_TOLERANCE
