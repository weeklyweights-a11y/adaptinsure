"""Abstract base adapter and batch transform result types."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import ValidationError

from src.exceptions import AdaptInsureError, DiscoveryError, MappingError, SchemaValidationError
from src.schema.models import Claim
from src.schema.validators import ValidationWarning, validate_claim_consistency

logger = logging.getLogger(__name__)


@dataclass
class TransformResult:
    """Outcome of processing a batch of raw records through an adapter."""

    successful: list[tuple[Claim, list[ValidationWarning]]] = field(default_factory=list)
    failed: list[tuple[dict[str, object], AdaptInsureError]] = field(default_factory=list)
    total_records: int = 0
    success_count: int = 0
    failure_count: int = 0

    def __post_init__(self) -> None:
        """Compute record counts from success and failure lists."""
        self.success_count = len(self.successful)
        self.failure_count = len(self.failed)
        self.total_records = self.success_count + self.failure_count


class BaseAdapter(ABC):
    """Abstract adapter contract for carrier-specific claim ingestion."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of this adapter."""

    @property
    @abstractmethod
    def source_system(self) -> str:
        """Identifier for the source CMS or carrier."""

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Input formats this adapter handles (e.g. json, xml, csv)."""

    @abstractmethod
    def parse_raw(self, raw_input: str | bytes) -> list[dict[str, object]]:
        """Parse raw input into a list of raw record dicts."""
        raise NotImplementedError

    @abstractmethod
    def map_record(self, raw_record: dict[str, object]) -> dict[str, object]:
        """Map a raw record to universal schema field names."""
        raise NotImplementedError

    def validate_record(
        self,
        mapped_record: dict[str, object],
    ) -> tuple[Claim, list[ValidationWarning]]:
        """Validate mapped record and return claim plus consistency warnings."""
        try:
            claim = Claim.model_validate_json(
                json.dumps(mapped_record, default=str),
            )
        except ValidationError as exc:
            raise SchemaValidationError(
                error_code="SCHEMA_VALIDATION_FAILED",
                message="Mapped record failed universal schema validation",
                details={"errors": exc.errors()},
            ) from exc
        warnings = validate_claim_consistency(claim)
        return claim, warnings

    def transform_batch(self, raw_input: str | bytes) -> TransformResult:
        """Parse, map, and validate all records; collect successes and failures."""
        result = TransformResult()
        try:
            raw_records = self.parse_raw(raw_input)
        except DiscoveryError as exc:
            logger.error("parse_raw failed for adapter %s: %s", self.name, exc)
            raise

        for raw_record in raw_records:
            record_id = raw_record.get("claim_id", raw_record.get("id", "unknown"))
            try:
                mapped = self.map_record(raw_record)
                claim, warnings = self.validate_record(mapped)
                result.successful.append((claim, warnings))
            except (DiscoveryError, MappingError, SchemaValidationError, ValueError) as exc:
                if isinstance(exc, AdaptInsureError):
                    error = exc
                else:
                    error = SchemaValidationError(
                        error_code="SCHEMA_VALIDATION_FAILED",
                        message=str(exc),
                        details={"record_id": record_id},
                    )
                logger.error(
                    "Record processing failed for adapter %s record %s: %s",
                    self.name,
                    record_id,
                    error,
                )
                result.failed.append((raw_record, error))
            except ValidationError as exc:
                error = SchemaValidationError(
                    error_code="SCHEMA_VALIDATION_FAILED",
                    message="Mapped record failed universal schema validation",
                    details={"record_id": record_id, "errors": exc.errors()},
                )
                logger.error(
                    "Validation failed for adapter %s record %s: %s",
                    self.name,
                    record_id,
                    error,
                )
                result.failed.append((raw_record, error))

        result.__post_init__()
        return result
