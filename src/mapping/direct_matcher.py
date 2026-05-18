"""Rule-based direct field matcher for the Mapping Engine."""

from __future__ import annotations

import re

from src.discovery.profile import FieldInfo
from src.mapping.config import FieldMapping, MatchType
from src.mapping.schema_registry import get_universal_schema_fields, schema_leaf

_PREFIXES = ("clm_", "pol_", "cc_", "ins_")

_ABBREVIATIONS: dict[str, str] = {
    "nbr": "number",
    "dt": "date",
    "amt": "amount",
    "nm": "name",
    "nme": "name",
    "addr": "address",
    "desc": "description",
    "sts": "status",
    "stat": "status",
    "cd": "code",
    "tp": "type",
    "typ": "type",
    "tot": "total",
    "rsv": "reserved",
    "res": "reserved",
    "pmt": "paid",
}

_PAID_SUFFIX_TOKENS = frozenset({"pd_amt", "pd_pmt", "pdamt", "pdpmt"})

_AMBIGUOUS_LEAVES = frozenset({"status"})

_ENTITY_PRIORITY = ("claim", "exposure", "claimant", "transaction", "policy")

_RULE_CONFIDENCE: list[tuple[str, float]] = [
    ("exact", 0.95),
    ("case_insensitive", 0.90),
    ("normalized", 0.85),
    ("prefix_strip", 0.75),
    ("abbreviation", 0.70),
]


def _normalize_key(name: str) -> str:
    """Lowercase and remove underscores for comparison."""
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return snake.lower().replace("_", "")


def _to_snake_lower(name: str) -> str:
    """Convert camelCase/PascalCase to lowercase snake_case."""
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return snake.lower()


def _is_pascal_case(name: str) -> bool:
    """True when the name starts with an uppercase letter (PascalCase)."""
    return bool(name) and name[0].isupper() and any(c.islower() for c in name[1:])


def _strip_prefixes(name: str) -> str:
    """Remove known insurance system prefixes."""
    lowered = name.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            return name[len(prefix) :]
    return name


def _expand_abbreviations(name: str) -> str:
    """Expand token abbreviations; never map bare pd to paid."""
    tokens = re.split(r"[_\s]+", name.lower())
    expanded: list[str] = []
    for token in tokens:
        if token in _PAID_SUFFIX_TOKENS:
            expanded.extend(["paid", "amount"])
            continue
        if token == "pd":
            expanded.append("pd")
            continue
        expanded.append(_ABBREVIATIONS.get(token, token))
    return "_".join(expanded)


def _candidate_paths(
    source_name: str,
    schema_fields: dict[str, str],
) -> list[tuple[str, str, float]]:
    """Return (path, rule, confidence) candidates for a source name."""
    variants: list[tuple[str, str, float]] = []
    base = source_name
    attempts: list[tuple[str, str, float]] = [
        (base, "exact", 0.95),
        (base, "case_insensitive", 0.90),
        (base, "normalized", 0.85),
    ]
    stripped = _strip_prefixes(base)
    if stripped != base:
        expanded = _expand_abbreviations(stripped)
        attempts.append((stripped, "prefix_strip", 0.75))
        if expanded != stripped.lower():
            attempts.append((expanded, "prefix_strip", 0.75))
            attempts.append((expanded, "abbreviation", 0.70))
    elif _expand_abbreviations(stripped) != stripped.lower():
        attempts.append((_expand_abbreviations(stripped), "abbreviation", 0.70))

    seen_keys: set[str] = set()
    for variant, rule, confidence in attempts:
        key = f"{rule}:{variant.lower()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        for path in schema_fields:
            leaf = schema_leaf(path)
            leaf_norm = _normalize_key(leaf)
            norm = _normalize_key(variant)
            if rule == "exact" and variant == leaf:
                variants.append((path, rule, confidence))
            elif (
                rule == "case_insensitive"
                and _to_snake_lower(variant) == leaf.lower()
                and _is_pascal_case(variant)
            ):
                variants.append((path, rule, confidence))
            elif rule == "normalized" and norm == leaf_norm:
                variants.append((path, rule, confidence))
            elif rule in {"prefix_strip", "abbreviation"} and (
                norm == leaf_norm
                or (leaf_norm.endswith(norm) and len(norm) >= 3)
            ):
                variants.append((path, rule, confidence))
    return variants


def _resolve_tie(
    source_name: str,
    candidates: list[tuple[str, str, float]],
) -> str | None:
    """Pick one target when multiple paths share the same match strength."""
    leaf = schema_leaf(candidates[0][0])
    if leaf in _AMBIGUOUS_LEAVES:
        return None
    paths = {c[0] for c in candidates}
    if source_name.lower().startswith("clm_") and "claim.claim_number" in paths:
        return "claim.claim_number"
    if len({schema_leaf(p) for p in paths}) > 1:
        return None
    for entity in _ENTITY_PRIORITY:
        for path in paths:
            if path.startswith(f"{entity}."):
                return path
    return sorted(paths)[0]


class DirectMatcher:
    """Match client fields to universal schema paths using deterministic rules."""

    def __init__(self, schema_fields: dict[str, str] | None = None) -> None:
        """Initialize with optional pre-built schema field map."""
        self._schema_fields = schema_fields or get_universal_schema_fields()

    def match(self, fields: list[FieldInfo]) -> list[FieldMapping]:
        """Return direct mappings for fields with unambiguous rule matches."""
        mappings: list[FieldMapping] = []
        for field in fields:
            candidates = _candidate_paths(field.source_name, self._schema_fields)
            if not candidates:
                continue
            best_confidence = max(c[2] for c in candidates)
            top = [c for c in candidates if c[2] == best_confidence]
            unique_paths = {c[0] for c in top}
            if len(unique_paths) != 1:
                path = _resolve_tie(field.source_name, top)
                if path is None:
                    continue
                rule = top[0][1]
                confidence = top[0][2]
            else:
                path, rule, confidence = top[0]
            mappings.append(
                FieldMapping(
                    source_field=field.source_name,
                    source_path=field.nesting_path,
                    target_field=path,
                    match_type=MatchType.DIRECT,
                    confidence=confidence,
                    reasoning=f"Direct match via {rule} rule",
                    transform=None,
                )
            )
        return mappings
