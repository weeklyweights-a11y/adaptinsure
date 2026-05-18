"""Aggregate confidence statistics for mapping runs."""

from __future__ import annotations

from src.mapping.config import ConfidenceSummary, FieldMapping, GapInfo


class ConfidenceScorer:
    """Compute ConfidenceSummary from mappings and gaps."""

    def compute_summary(
        self,
        mappings: list[FieldMapping],
        gaps: list[GapInfo],
        total_source_fields: int,
    ) -> ConfidenceSummary:
        """Build aggregate confidence statistics."""
        mapped_count = len(mappings)
        unmapped = max(0, total_source_fields - mapped_count)
        high = sum(1 for m in mappings if m.confidence >= 0.8)
        medium = sum(1 for m in mappings if 0.5 <= m.confidence < 0.8)
        low = sum(1 for m in mappings if m.confidence < 0.5)
        average = (
            sum(m.confidence for m in mappings) / len(mappings) if mappings else 0.0
        )
        has_critical = any(g.severity == "critical" for g in gaps)
        requires_review = low > 0 or has_critical
        return ConfidenceSummary(
            total_fields=total_source_fields,
            mapped_fields=mapped_count,
            unmapped_fields=unmapped,
            high_confidence_count=high,
            medium_confidence_count=medium,
            low_confidence_count=low,
            average_confidence=round(average, 4),
            requires_review=requires_review,
        )
