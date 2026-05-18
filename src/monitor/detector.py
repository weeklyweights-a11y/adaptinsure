"""Drift detector orchestrator."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.discovery.profile import ClientProfile
from src.exceptions import MonitorError
from src.llm.client import LLMClient
from src.mapping.config import MappingConfig
from src.monitor.alerter import Alert, AlertGenerator
from src.monitor.approval import ApprovalWorkflow
from src.monitor.codes import MON_CONFIG_NOT_FOUND, MON_SCHEMA_NOT_FOUND
from src.monitor.config_loader import load_mapping_config
from src.monitor.differ import SchemaDiff, SchemaDiffer
from src.monitor.expected_schema import ExpectedSchema, default_schema_path
from src.monitor.proposer import FixProposer, ProposedFix
from src.monitor.records import parse_incoming_records

logger = logging.getLogger(__name__)


class DriftReport(BaseModel):
    """Result of a drift check run."""

    model_config = ConfigDict(strict=True)

    client_name: Annotated[str, Field(description="Client checked")]
    checked_at: Annotated[datetime, Field(description="Check time UTC")]
    records_analyzed: Annotated[int, Field(ge=0)]
    drifts_found: Annotated[int, Field(ge=0)]
    critical_count: Annotated[int, Field(ge=0)]
    warning_count: Annotated[int, Field(ge=0)]
    info_count: Annotated[int, Field(ge=0)]
    drifts: Annotated[list[SchemaDiff], Field(default_factory=list)]
    alerts: Annotated[list[Alert], Field(default_factory=list)]
    proposed_fixes: Annotated[list[ProposedFix], Field(default_factory=list)]
    status: Annotated[str, Field(description="clean, drifted, or error")]


class DriftDetector:
    """Main entry point for on-demand drift monitoring."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        schema_dir: Path | None = None,
        approval: ApprovalWorkflow | None = None,
        differ: SchemaDiffer | None = None,
        alerter: AlertGenerator | None = None,
        proposer: FixProposer | None = None,
    ) -> None:
        """Initialize detector with optional dependency overrides."""
        self._schema_dir = schema_dir or Path("data/schemas")
        self._differ = differ or SchemaDiffer()
        self._alerter = alerter or AlertGenerator()
        self._proposer = proposer or FixProposer(llm_client)
        self._approval = approval or ApprovalWorkflow(schema_dir=self._schema_dir)

    def load_expected_schema(self, client_name: str) -> ExpectedSchema:
        """Load expected schema from disk."""
        path = default_schema_path(client_name, self._schema_dir)
        if not path.is_file():
            raise MonitorError(
                MON_SCHEMA_NOT_FOUND,
                f"Expected schema not found for {client_name!r}",
                details={"path": str(path)},
            )
        return ExpectedSchema.model_validate_json(path.read_text(encoding="utf-8"))

    def save_expected_schema(self, schema: ExpectedSchema) -> None:
        """Persist expected schema to disk."""
        self._schema_dir.mkdir(parents=True, exist_ok=True)
        path = default_schema_path(schema.client_name, self._schema_dir)
        path.write_text(schema.model_dump_json(), encoding="utf-8")

    def bootstrap_baseline(
        self,
        client_name: str,
        mapping_config: MappingConfig,
        profile: ClientProfile,
    ) -> ExpectedSchema:
        """Create and save initial expected schema for a client."""
        schema = ExpectedSchema.from_mapping_config(mapping_config, profile)
        schema = schema.model_copy(update={"client_name": client_name})
        self.save_expected_schema(schema)
        return schema

    async def check(
        self,
        client_name: str,
        incoming_data: str | bytes,
        mapping_config: MappingConfig | None = None,
        profile: ClientProfile | None = None,
    ) -> DriftReport:
        """Run full drift detection pipeline."""
        checked_at = datetime.now(UTC)
        try:
            expected = self.load_expected_schema(client_name)
        except MonitorError:
            raise

        config = mapping_config
        if config is None:
            try:
                config = load_mapping_config(client_name)
            except MonitorError as exc:
                if exc.error_code != MON_CONFIG_NOT_FOUND:
                    raise
                logger.warning("Mapping config missing for %s: %s", client_name, exc.message)
                config = None

        t0 = time.perf_counter()
        _fmt, records = parse_incoming_records(incoming_data)
        logger.info("Parsed %s records in %.1fms", len(records), (time.perf_counter() - t0) * 1000)

        if profile is not None:
            self._approval.set_client_context(client_name, profile, records)

        t1 = time.perf_counter()
        drifts = self._differ.diff(expected, records)
        elapsed_ms = (time.perf_counter() - t1) * 1000
        logger.info("Diff found %s drifts in %.1fms", len(drifts), elapsed_ms)

        if not drifts:
            updated = expected.model_copy(
                update={
                    "last_validated_at": datetime.now(UTC),
                    "record_count_baseline": len(records),
                }
            )
            self.save_expected_schema(updated)
            return DriftReport(
                client_name=client_name,
                checked_at=checked_at,
                records_analyzed=len(records),
                drifts_found=0,
                critical_count=0,
                warning_count=0,
                info_count=0,
                status="clean",
            )

        alerts = self._alerter.generate_alerts(drifts, client_name, config)
        proposed: list[ProposedFix] = []

        for diff in drifts:
            if diff.severity not in {"critical", "warning"}:
                continue
            if config is None:
                continue
            try:
                fix = await self._proposer.propose_fix(diff, config, expected)
                proposed.append(fix)
                alert = next(
                    (a for a in alerts if a.diff.field_name == diff.field_name),
                    alerts[0] if alerts else None,
                )
                if alert is None:
                    continue
                self._approval.submit(fix, alert)
            except Exception as exc:
                logger.warning("Fix proposal failed for %s: %s", diff.field_name, exc)

        critical = sum(1 for d in drifts if d.severity == "critical")
        warning = sum(1 for d in drifts if d.severity == "warning")
        info = sum(1 for d in drifts if d.severity == "info")

        return DriftReport(
            client_name=client_name,
            checked_at=checked_at,
            records_analyzed=len(records),
            drifts_found=len(drifts),
            critical_count=critical,
            warning_count=warning,
            info_count=info,
            drifts=drifts,
            alerts=alerts,
            proposed_fixes=proposed,
            status="drifted",
        )
