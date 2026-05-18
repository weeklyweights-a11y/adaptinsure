"""Approval workflow for proposed drift fixes."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.discovery.profile import ClientProfile
from src.exceptions import MonitorError
from src.generator.registry import AdapterRegistry
from src.mapping.config import MappingConfig
from src.monitor.alerter import Alert
from src.monitor.codes import MON_FIX_NOT_FOUND, MON_PERSIST_FAILED
from src.monitor.config_applier import apply_config_changes
from src.monitor.config_loader import load_mapping_config, write_mapping_config
from src.monitor.expected_schema import ExpectedSchema, refresh_expected_schema
from src.monitor.proposer import ConfigChange, ProposedFix

logger = logging.getLogger(__name__)


class PendingFix(BaseModel):
    """A fix awaiting human approval."""

    model_config = ConfigDict(strict=True)

    fix_id: Annotated[str, Field(description="Unique fix id")]
    proposed_fix: Annotated[ProposedFix, Field(description="Proposed change")]
    alert: Annotated[Alert, Field(description="Linked alert")]
    status: Annotated[str, Field(description="Workflow status")]
    submitted_at: Annotated[datetime, Field(description="Submission time UTC")]
    reviewed_at: Annotated[datetime | None, Field(default=None)]
    reviewed_by: Annotated[str | None, Field(default=None)]
    rejection_reason: Annotated[str | None, Field(default=None)]


class AppliedFix(BaseModel):
    """Result of applying an approved fix."""

    model_config = ConfigDict(strict=True)

    fix_id: Annotated[str, Field(description="Fix id")]
    original_config: Annotated[MappingConfig, Field(description="Config before fix")]
    updated_config: Annotated[MappingConfig, Field(description="Config after fix")]
    changes_applied: Annotated[list[ConfigChange], Field(description="Changes applied")]
    applied_at: Annotated[datetime, Field(description="Application time UTC")]


class FixHistoryEntry(BaseModel):
    """History record for a fix."""

    model_config = ConfigDict(strict=True)

    fix_id: Annotated[str, Field(description="Fix id")]
    client_name: Annotated[str, Field(description="Client name")]
    diff_type: Annotated[str, Field(description="Drift type")]
    status: Annotated[str, Field(description="Final status")]
    submitted_at: Annotated[datetime, Field(description="Submitted at")]
    resolved_at: Annotated[datetime | None, Field(default=None)]
    summary: Annotated[str, Field(description="One-line summary")]


class ApprovalWorkflow:
    """Queue and apply proposed mapping fixes."""

    def __init__(
        self,
        pending_path: Path | None = None,
        *,
        schema_dir: Path | None = None,
        generator: object | None = None,
        registry: AdapterRegistry | None = None,
    ) -> None:
        """Initialize workflow with optional paths for tests."""
        self._pending_path = pending_path or Path("data/pending_fixes.json")
        self._schema_dir = schema_dir or Path("data/schemas")
        self._generator = generator
        self._registry = registry
        self._profiles: dict[str, ClientProfile] = {}
        self._last_records: dict[str, list[dict[str, object]]] = {}
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)

    def set_client_context(
        self,
        client_name: str,
        profile: ClientProfile,
        records: list[dict[str, object]] | None = None,
    ) -> None:
        """Store profile and records for schema refresh on approve."""
        self._profiles[client_name] = profile
        if records is not None:
            self._last_records[client_name] = records

    def submit(self, fix: ProposedFix, alert: Alert) -> str:
        """Add fix to pending queue and return fix_id."""
        fix_id = alert.alert_id
        status = "auto_approved" if fix.auto_applicable else "pending"
        pending = PendingFix(
            fix_id=fix_id,
            proposed_fix=fix,
            alert=alert,
            status=status,
            submitted_at=datetime.now(UTC),
        )
        queue = self._load_queue()
        queue[fix_id] = json.loads(pending.model_dump_json())
        self._save_queue(queue)
        return fix_id

    def list_pending(self) -> list[PendingFix]:
        """Return fixes awaiting approval."""
        result: list[PendingFix] = []
        for v in self._load_queue().values():
            if v.get("status") not in {"pending", "auto_approved"}:
                continue
            result.append(PendingFix.model_validate_json(json.dumps(v)))
        return result

    def approve(
        self,
        fix_id: str,
        *,
        profile: ClientProfile | None = None,
        records: list[dict[str, object]] | None = None,
    ) -> AppliedFix:
        """Apply fix, refresh baseline, regenerate adapter."""
        queue = self._load_queue()
        raw = queue.get(fix_id)
        if raw is None:
            raise MonitorError(MON_FIX_NOT_FOUND, f"Fix {fix_id!r} not found")
        pending = PendingFix.model_validate_json(json.dumps(raw))
        original = load_mapping_config(
            pending.alert.client_name,
            registry=self._registry,
        )
        updated = apply_config_changes(
            original,
            pending.proposed_fix.config_changes,
            pending.proposed_fix.fix_type,
        )
        pending.status = "approved"
        pending.reviewed_at = datetime.now(UTC)
        alert = pending.alert.model_copy(update={"resolved": True})
        pending = pending.model_copy(update={"alert": alert})
        queue[fix_id] = json.loads(pending.model_dump_json())
        self._save_queue(queue)

        client = pending.alert.client_name
        prof = profile or self._profiles.get(client)
        recs = records if records is not None else self._last_records.get(client, [])
        if prof is not None:
            schema_path = self._schema_dir / f"{client.replace('/', '_')}.json"
            if schema_path.is_file():
                expected = ExpectedSchema.model_validate_json(
                    schema_path.read_text(encoding="utf-8")
                )
            else:
                expected = ExpectedSchema.from_mapping_config(original, prof)
            refreshed = refresh_expected_schema(
                expected,
                updated,
                prof,
                record_count=len(recs) if recs else None,
            )
            self._schema_dir.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(refreshed.model_dump_json(), encoding="utf-8")

        gen_dir = Path("generated")
        if self._registry:
            adapters = self._registry.list_adapters()
            if adapters:
                gen_dir = adapters[0].adapter_file.parent
        write_mapping_config(updated, gen_dir)

        if self._generator is not None:
            result = self._generator.generate(updated, gen_dir)
        else:
            from src.generator.engine import GeneratorEngine

            result = GeneratorEngine().generate(updated, gen_dir)

        reg = self._registry or AdapterRegistry()
        reg.register(result, updated)

        pending.status = "applied"
        queue[fix_id] = json.loads(pending.model_dump_json())
        self._save_queue(queue)
        logger.info("Approved fix %s for client %s", fix_id, client)

        self._append_history(pending, "applied")
        return AppliedFix(
            fix_id=fix_id,
            original_config=original,
            updated_config=updated,
            changes_applied=pending.proposed_fix.config_changes,
            applied_at=datetime.now(UTC),
        )

    def reject(self, fix_id: str, reason: str) -> None:
        """Reject a pending fix."""
        queue = self._load_queue()
        raw = queue.get(fix_id)
        if raw is None:
            raise MonitorError(MON_FIX_NOT_FOUND, f"Fix {fix_id!r} not found")
        pending = PendingFix.model_validate_json(json.dumps(raw))
        pending = pending.model_copy(
            update={
                "status": "rejected",
                "reviewed_at": datetime.now(UTC),
                "rejection_reason": reason,
            }
        )
        queue[fix_id] = json.loads(pending.model_dump_json())
        self._save_queue(queue)
        logger.info("Rejected fix %s: %s", fix_id, reason)
        self._append_history(pending, "rejected")

    def get_history(self) -> list[FixHistoryEntry]:
        """Return all fix history entries."""
        path = self._pending_path.parent / "fix_history.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [FixHistoryEntry.model_validate(e) for e in data]

    def _append_history(self, pending: PendingFix, status: str) -> None:
        """Append entry to fix history log."""
        path = self._pending_path.parent / "fix_history.json"
        entries: list[dict[str, object]] = []
        if path.is_file():
            entries = json.loads(path.read_text(encoding="utf-8"))
        entries.append(
            FixHistoryEntry(
                fix_id=pending.fix_id,
                client_name=pending.alert.client_name,
                diff_type=pending.proposed_fix.diff.diff_type.value,
                status=status,
                submitted_at=pending.submitted_at,
                resolved_at=datetime.now(UTC),
                summary=pending.proposed_fix.description[:120],
            ).model_dump(mode="json")
        )
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _load_queue(self) -> dict[str, object]:
        """Load pending fixes from JSON."""
        if not self._pending_path.is_file():
            return {}
        try:
            return json.loads(self._pending_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MonitorError(
                MON_PERSIST_FAILED,
                f"Invalid pending fixes file: {exc}",
            ) from exc

    def _save_queue(self, queue: dict[str, object]) -> None:
        """Persist pending fixes to JSON."""
        try:
            self._pending_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
        except OSError as exc:
            raise MonitorError(
                MON_PERSIST_FAILED,
                f"Failed to save pending fixes: {exc}",
            ) from exc
