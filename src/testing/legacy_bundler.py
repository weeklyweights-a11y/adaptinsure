"""Join legacy multi-file CSV exports into bundled claim records."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LegacyBundle:
    """Legacy carrier sample bundle."""

    claims_bytes: bytes
    data_dictionary_text: str
    joined_records: list[dict[str, object]]


def load_legacy_bundle(samples_dir: Path) -> LegacyBundle:
    """Load and join legacy CSV files on CLM_NBR."""
    base = samples_dir / "legacy_carrier"
    claims_bytes = (base / "claims.csv").read_bytes()
    dd_path = base / "data_dictionary.md"
    data_dictionary_text = dd_path.read_text(encoding="latin-1") if dd_path.exists() else ""

    claims = _read_pipe_csv(claims_bytes)
    exposures = _read_pipe_csv((base / "exposures.csv").read_bytes())
    contacts = _read_pipe_csv((base / "contacts.csv").read_bytes())
    transactions = _read_pipe_csv((base / "transactions.csv").read_bytes())

    exp_by_clm: dict[str, list[dict[str, object]]] = {}
    for row in exposures:
        key = str(row.get("CLM_NBR", ""))
        exp_by_clm.setdefault(key, []).append(row)

    cnt_by_clm: dict[str, list[dict[str, object]]] = {}
    for row in contacts:
        key = str(row.get("CLM_NBR", ""))
        cnt_by_clm.setdefault(key, []).append(row)

    txn_by_clm: dict[str, list[dict[str, object]]] = {}
    for row in transactions:
        key = str(row.get("CLM_NBR", ""))
        txn_by_clm.setdefault(key, []).append(row)

    joined: list[dict[str, object]] = []
    for claim in claims:
        clm_nbr = str(claim.get("CLM_NBR", ""))
        record = dict(claim)
        record["_exposures"] = exp_by_clm.get(clm_nbr, [])
        record["_contacts"] = cnt_by_clm.get(clm_nbr, [])
        record["_transactions"] = txn_by_clm.get(clm_nbr, [])
        joined.append(record)

    return LegacyBundle(
        claims_bytes=claims_bytes,
        data_dictionary_text=data_dictionary_text,
        joined_records=joined,
    )


def _read_pipe_csv(data: bytes) -> list[dict[str, object]]:
    text = data.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    return [dict(row) for row in reader]
