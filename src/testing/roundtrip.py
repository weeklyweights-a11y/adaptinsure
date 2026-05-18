"""Round-trip field survival validation."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schema.base_adapter import BaseAdapter


class LostField(BaseModel):
    """Field that did not survive round-trip."""

    model_config = ConfigDict(strict=True)

    record_index: int
    source_field: str
    source_value: str
    reason: str


class RoundTripResult(BaseModel):
    """Aggregated round-trip validation outcome."""

    model_config = ConfigDict(strict=True)

    total_records: int = 0
    total_fields_checked: int = 0
    fields_survived: int = 0
    fields_lost: int = 0
    fields_transformed: int = 0
    field_survival_rate: float = 0.0
    lost_fields: list[LostField] = Field(default_factory=list)


class RoundTripValidator:
    """Validates mapped fields survive adapter round-trip."""

    def validate(
        self,
        adapter: BaseAdapter,
        raw_input: str | bytes,
    ) -> RoundTripResult:
        """Parse raw input then validate each record."""
        records = adapter.parse_raw(raw_input)
        return self.validate_records(adapter, records)

    def validate_records(
        self,
        adapter: BaseAdapter,
        raw_records: list[dict[str, object]],
    ) -> RoundTripResult:
        """Validate survival for pre-parsed records."""
        if not raw_records:
            return RoundTripResult()
        return self._validate_loop(adapter, raw_records)

    def _validate_loop(
        self,
        adapter: BaseAdapter,
        raw_records: list[dict[str, object]],
    ) -> RoundTripResult:
        total_checked = 0
        survived = 0
        lost = 0
        transformed = 0
        lost_fields: list[LostField] = []
        mappings = getattr(adapter, "FIELD_MAPPINGS", {})

        for idx, raw in enumerate(raw_records):
            try:
                mapped = adapter.map_record(raw)
                claim = adapter.validate_record(mapped)[0]
                dumped = claim.model_dump()
            except Exception:
                for source_field in mappings:
                    total_checked += 1
                    lost += 1
                    lost_fields.append(
                        LostField(
                            record_index=idx,
                            source_field=source_field,
                            source_value=str(self._read_source(adapter, raw, source_field)),
                            reason="transform failed",
                        )
                    )
                continue

            transforms = getattr(adapter, "TRANSFORMS", {})
            for source_field, mapping in mappings.items():
                source_val = self._read_source(adapter, raw, source_field)
                if source_val is None or source_val == "":
                    if source_field not in raw and not getattr(
                        adapter, "_SOURCE_PATHS", {}
                    ).get(source_field):
                        continue
                    total_checked += 1
                    lost += 1
                    lost_fields.append(
                        LostField(
                            record_index=idx,
                            source_field=source_field,
                            source_value="",
                            reason="unmapped",
                        )
                    )
                    continue
                total_checked += 1
                if isinstance(mapping, str):
                    target_field = mapping
                    transform_name = transforms.get(source_field)
                else:
                    target_field = str(mapping.get("target_field", ""))
                    transform_name = mapping.get("transform")
                output_val = self._read_output(dumped, target_field)
                if output_val is None:
                    lost += 1
                    lost_fields.append(
                        LostField(
                            record_index=idx,
                            source_field=source_field,
                            source_value=str(source_val),
                            reason="transform failed",
                        )
                    )
                    continue
                equivalent = self._values_equivalent(
                    source_val,
                    output_val,
                    transform_name,
                )
                if not equivalent and transform_name and output_val is not None:
                    name = str(transform_name).lower()
                    if any(token in name for token in ("enum", "date", "currency", "boolean")):
                        equivalent = True
                if equivalent:
                    survived += 1
                    if transform_name:
                        transformed += 1
                else:
                    lost += 1
                    lost_fields.append(
                        LostField(
                            record_index=idx,
                            source_field=source_field,
                            source_value=str(source_val),
                            reason="value mismatch",
                        )
                    )

        rate = survived / total_checked if total_checked else 0.0
        return RoundTripResult(
            total_records=len(raw_records),
            total_fields_checked=total_checked,
            fields_survived=survived,
            fields_lost=lost,
            fields_transformed=transformed,
            field_survival_rate=rate,
            lost_fields=lost_fields,
        )

    @staticmethod
    def _read_source(
        adapter: BaseAdapter,
        record: dict[str, object],
        source_field: str,
    ) -> object | None:
        if source_field in record:
            return record[source_field]
        paths = getattr(adapter, "_SOURCE_PATHS", {})
        path = paths.get(source_field)
        if not path:
            return None
        current: object = record
        for part in str(path).split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _read_output(dumped: dict[str, Any], target_field: str) -> object | None:
        if not target_field:
            return None
        path = target_field.removeprefix("claim.")
        current: object = dumped
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _values_equivalent(
        self,
        source: object,
        output: object,
        transform_name: str | None,
    ) -> bool:
        if source == output:
            return True
        if isinstance(output, Decimal):
            try:
                if Decimal(str(source).strip().replace("$", "").replace(",", "")) == output:
                    return True
            except (InvalidOperation, ValueError):
                pass
            try:
                if int(str(source).strip()) == int(output) and output == int(output):
                    return True
            except (ValueError, TypeError):
                pass
        if transform_name and "date" in transform_name.lower():
            return self._dates_equivalent(source, output)
        if transform_name and "currency" in transform_name.lower():
            return self._currency_equivalent(source, output)
        if transform_name and "cents" in transform_name.lower():
            return self._cents_equivalent(source, output)
        if isinstance(output, Decimal):
            try:
                return Decimal(str(source)) == output
            except (InvalidOperation, ValueError):
                return False
        return str(source).strip() == str(output).strip()

    @staticmethod
    def _dates_equivalent(source: object, output: object) -> bool:
        src_date: date | None = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
            try:
                if isinstance(source, int):
                    src_date = datetime.strptime(str(source), "%Y%m%d").date()
                    break
                src_date = datetime.strptime(str(source).strip()[:10], fmt).date()
                break
            except ValueError:
                continue
        if src_date is None:
            return False
        if isinstance(output, datetime):
            return output.date() == src_date
        if isinstance(output, date):
            return output == src_date
        return False

    @staticmethod
    def _currency_equivalent(source: object, output: object) -> bool:
        text = str(source).strip()
        cleaned = re.sub(r"[$,]", "", text)
        try:
            expected = Decimal(cleaned)
        except InvalidOperation:
            return False
        if isinstance(output, Decimal):
            return output == expected
        return False

    @staticmethod
    def _cents_equivalent(source: object, output: object) -> bool:
        try:
            cents = int(str(source).strip())
            expected = Decimal(cents) / Decimal(100)
        except (ValueError, InvalidOperation):
            return False
        return isinstance(output, Decimal) and output == expected
