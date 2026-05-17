"""Tests for AdaptInsure exception hierarchy."""

from __future__ import annotations

import pytest

from src.exceptions import (
    AdaptInsureError,
    ConfigError,
    DiscoveryError,
    GenerationError,
    LLMError,
    MappingError,
    MonitorError,
    SchemaValidationError,
)
from src.exceptions import TestHarnessError as HarnessTestError

# Alias avoids pytest mistaking TestHarnessError for a test class.


class TestAdaptInsureError:
    """Base and subclass exception behavior."""

    def test_adapt_insure_error_raise_and_catch(self) -> None:
        with pytest.raises(AdaptInsureError):
            raise AdaptInsureError("BASE_001", "base failure")

    @pytest.mark.parametrize(
        "error_cls",
        [
            SchemaValidationError,
            DiscoveryError,
            MappingError,
            GenerationError,
            HarnessTestError,
            MonitorError,
            LLMError,
            ConfigError,
        ],
    )
    def test_subclass_catchable_as_self_and_base(
        self,
        error_cls: type[AdaptInsureError],
    ) -> None:
        err = error_cls("PREFIX_CODE", "message", {"key": "value"})
        with pytest.raises(error_cls):
            raise err
        with pytest.raises(AdaptInsureError):
            raise error_cls("PREFIX_CODE", "again")

    def test_error_code_stored(self) -> None:
        err = DiscoveryError("DISC_PARSE", "parse failed")
        assert err.error_code == "DISC_PARSE"

    def test_message_stored(self) -> None:
        err = MappingError("MAP_001", "map failed")
        assert err.message == "map failed"

    def test_details_stored(self) -> None:
        err = SchemaValidationError("SCHEMA_001", "invalid", {"field": "x"})
        assert err.details == {"field": "x"}

    def test_details_default_none(self) -> None:
        err = ConfigError("CFG_001", "missing key")
        assert err.details is None

    def test_str_includes_error_code_and_message(self) -> None:
        err = LLMError("LLM_TIMEOUT", "request timed out")
        text = str(err)
        assert "LLM_TIMEOUT" in text
        assert "request timed out" in text
