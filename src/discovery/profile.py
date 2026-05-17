"""ClientProfile and FieldInfo models for the Discovery Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InferredType = Literal[
    "string",
    "integer",
    "decimal",
    "boolean",
    "date",
    "datetime",
    "array",
    "object",
    "null",
    "unknown",
]

SourceFormat = Literal["json", "xml", "csv", "fixed_width", "unknown"]

ALLOWED_INFERRED_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "integer",
        "decimal",
        "boolean",
        "date",
        "datetime",
        "array",
        "object",
        "null",
        "unknown",
    }
)


class FieldInfo(BaseModel):
    """Describes a single field in client data."""

    model_config = ConfigDict(strict=True)

    source_name: Annotated[str, Field(description="Field name as it appears in client data")]
    inferred_type: Annotated[InferredType, Field(description="Inferred data type")]
    sample_values: Annotated[
        list[str],
        Field(default_factory=list, description="Up to 5 sample values as strings"),
    ]
    nullable: Annotated[bool, Field(default=False, description="Whether null/empty was observed")]
    format_pattern: Annotated[
        str | None,
        Field(default=None, description="Detected format pattern"),
    ]
    description: Annotated[
        str | None,
        Field(default=None, description="From data dictionary or API docs"),
    ]
    insurance_annotation: Annotated[
        str | None,
        Field(default=None, description="LLM-inferred insurance meaning"),
    ]
    confidence: Annotated[
        float,
        Field(default=0.5, ge=0.0, le=1.0, description="Inference confidence"),
    ]
    nesting_path: Annotated[
        str | None,
        Field(default=None, description="Dot-path for nested fields"),
    ]

    @field_validator("inferred_type")
    @classmethod
    def validate_inferred_type(cls, value: str) -> str:
        """Ensure inferred_type is one of the allowed values."""
        if value not in ALLOWED_INFERRED_TYPES:
            msg = f"inferred_type must be one of {sorted(ALLOWED_INFERRED_TYPES)}"
            raise ValueError(msg)
        return value

    @field_validator("sample_values")
    @classmethod
    def cap_sample_values(cls, value: list[str]) -> list[str]:
        """Limit sample values to at most five."""
        return value[:5]


class ClientProfile(BaseModel):
    """Complete description of a client's data format and fields."""

    model_config = ConfigDict(strict=True)

    client_name: Annotated[str, Field(description="Client or carrier identifier")]
    source_format: Annotated[SourceFormat, Field(description="Detected source format")]
    detected_encoding: Annotated[str, Field(description="Character encoding used")]
    total_records_sampled: Annotated[int, Field(ge=0, description="Records analyzed")]
    total_fields_detected: Annotated[int, Field(ge=0, description="Number of fields detected")]
    fields: Annotated[list[FieldInfo], Field(default_factory=list)]
    nested_structures: Annotated[
        list[str],
        Field(default_factory=list, description="Nested object/array names"),
    ]
    notes: Annotated[list[str], Field(default_factory=list, description="Observations")]
    raw_sample: Annotated[
        dict[str, Any] | str | None,
        Field(default=None, description="Single raw record for reference"),
    ]
    created_at: Annotated[datetime, Field(description="Profile creation timestamp (UTC)")]
    warnings: Annotated[list[str], Field(default_factory=list, description="Discovery issues")]

    @model_validator(mode="after")
    def validate_field_count(self) -> ClientProfile:
        """Ensure total_fields_detected matches len(fields)."""
        if self.total_fields_detected != len(self.fields):
            msg = "total_fields_detected must equal len(fields)"
            raise ValueError(msg)
        return self
