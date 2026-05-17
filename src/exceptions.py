"""Custom exception hierarchy for AdaptInsure."""

from __future__ import annotations


class AdaptInsureError(Exception):
    """Base exception for the AdaptInsure platform."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize with error code, message, and optional details."""
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        """Return error_code and message for logging and APIs."""
        return f"[{self.error_code}] {self.message}"


class SchemaValidationError(AdaptInsureError):
    """Data does not match the universal schema."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize schema validation error with SCHEMA_ prefix convention."""
        super().__init__(error_code, message, details)


class DiscoveryError(AdaptInsureError):
    """Failed to analyze incoming data format."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize discovery error with DISC_ prefix convention."""
        super().__init__(error_code, message, details)


class MappingError(AdaptInsureError):
    """Failed to map client fields to universal schema."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize mapping error with MAP_ prefix convention."""
        super().__init__(error_code, message, details)


class GenerationError(AdaptInsureError):
    """Failed to generate adapter code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize generation error with GEN_ prefix convention."""
        super().__init__(error_code, message, details)


class TestHarnessError(AdaptInsureError):
    """Generated adapter failed testing."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize test harness error with TEST_ prefix convention."""
        super().__init__(error_code, message, details)


class MonitorError(AdaptInsureError):
    """Drift detection or alerting failed."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize monitor error with MON_ prefix convention."""
        super().__init__(error_code, message, details)


class LLMError(AdaptInsureError):
    """LLM call failed or returned invalid output."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize LLM error with LLM_ prefix convention."""
        super().__init__(error_code, message, details)


class ConfigError(AdaptInsureError):
    """Configuration is missing or invalid."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize config error with CFG_ prefix convention."""
        super().__init__(error_code, message, details)
