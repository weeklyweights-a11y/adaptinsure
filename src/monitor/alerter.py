"""Human-readable alert generation from schema diffs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.mapping.config import MappingConfig
from src.monitor.differ import DiffType, SchemaDiff

_SEVERITY_PREFIX = {
    "critical": "CRITICAL",
    "warning": "WARNING",
    "info": "INFO",
}


class Alert(BaseModel):
    """Alert describing a detected schema drift."""

    model_config = ConfigDict(strict=True)

    alert_id: Annotated[str, Field(description="Unique alert id")]
    client_name: Annotated[str, Field(description="Client identifier")]
    severity: Annotated[str, Field(description="critical, warning, or info")]
    title: Annotated[str, Field(description="One-line summary")]
    description: Annotated[str, Field(description="Detailed explanation")]
    diff: Annotated[SchemaDiff, Field(description="Underlying drift")]
    created_at: Annotated[datetime, Field(description="Alert creation UTC")]
    acknowledged: Annotated[bool, Field(default=False)]
    resolved: Annotated[bool, Field(default=False)]


class AlertGenerator:
    """Build alerts from schema diffs."""

    def generate_alerts(
        self,
        diffs: list[SchemaDiff],
        client_name: str,
        mapping_config: MappingConfig | None = None,
    ) -> list[Alert]:
        """Create alerts, grouping rename pairs when possible."""
        if not diffs:
            return []
        grouped = self._group_diffs(diffs)
        alerts: list[Alert] = []
        for group in grouped:
            primary = group[0]
            title = self._build_title(primary)
            prefix = _SEVERITY_PREFIX.get(primary.severity, "INFO")
            description = self._build_description(
                group, client_name, mapping_config
            )
            alerts.append(
                Alert(
                    alert_id=str(uuid.uuid4()),
                    client_name=client_name,
                    severity=primary.severity,
                    title=f"{prefix}: {title}",
                    description=description,
                    diff=primary,
                    created_at=datetime.now(UTC),
                )
            )
        return alerts

    def _group_diffs(self, diffs: list[SchemaDiff]) -> list[list[SchemaDiff]]:
        """Group rename-related removed+added pairs."""
        used: set[int] = set()
        groups: list[list[SchemaDiff]] = []

        for i, diff in enumerate(diffs):
            if i in used:
                continue
            if diff.diff_type == DiffType.FIELD_RENAMED and diff.suggested_rename:
                group = [diff]
                used.add(i)
                for j, other in enumerate(diffs):
                    if j in used:
                        continue
                    if (
                        other.diff_type == DiffType.FIELD_ADDED
                        and other.field_name == diff.suggested_rename
                    ):
                        group.append(other)
                        used.add(j)
                groups.append(group)
                continue
            groups.append([diff])
            used.add(i)
        return groups

    def _build_title(self, diff: SchemaDiff) -> str:
        """Build one-line alert title."""
        if diff.diff_type == DiffType.FIELD_RENAMED and diff.suggested_rename:
            return f"Field renamed: {diff.field_name} -> {diff.suggested_rename}"
        if diff.diff_type == DiffType.FIELD_REMOVED:
            return f"Field removed — '{diff.field_name}'"
        if diff.diff_type == DiffType.FIELD_ADDED:
            return f"New field detected — '{diff.field_name}'"
        if diff.diff_type == DiffType.FORMAT_CHANGED:
            return f"Format changed — '{diff.field_name}'"
        if diff.diff_type == DiffType.ENUM_VALUE_ADDED:
            return f"New enum value — '{diff.field_name}'"
        return f"{diff.diff_type.value} — '{diff.field_name}'"

    def _build_description(
        self,
        group: list[SchemaDiff],
        client_name: str,
        mapping_config: MappingConfig | None,
    ) -> str:
        """Build multi-line alert description."""
        diff = group[0]
        lines = [diff.description]
        lines.append(
            f"Affected: {diff.affected_records}/{diff.total_records} records "
            f"in the latest batch for {client_name}."
        )
        target = diff.target_field
        if target is None and mapping_config:
            for m in mapping_config.field_mappings:
                if m.source_field == diff.field_name:
                    target = m.target_field
                    break
        if target:
            req = "required" if target.startswith("claim.") else "optional"
            lines.append(
                f"This field maps to {target} ({req}). "
                f"Recommended action: review and approve the proposed fix."
            )
        return "\n".join(lines)
