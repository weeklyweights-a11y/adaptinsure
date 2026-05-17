"""Merge data dictionary fields into parsed discovery fields."""

from __future__ import annotations

from src.discovery.profile import FieldInfo


def merge_dictionary_fields(
    parsed_fields: list[FieldInfo],
    doc_fields: list[FieldInfo],
) -> list[FieldInfo]:
    """Merge dictionary metadata into parsed fields; append doc-only fields."""
    doc_by_name = {f.source_name.lower(): f for f in doc_fields}
    merged: list[FieldInfo] = []
    seen_names: set[str] = set()

    for field in parsed_fields:
        key = field.source_name.lower()
        seen_names.add(key)
        doc = doc_by_name.get(key)
        if doc:
            merged.append(
                field.model_copy(
                    update={
                        "description": doc.description or field.description,
                        "inferred_type": (
                            doc.inferred_type
                            if doc.inferred_type != "unknown"
                            else field.inferred_type
                        ),
                        "format_pattern": doc.format_pattern or field.format_pattern,
                    }
                )
            )
        else:
            merged.append(field)

    for doc_field in doc_fields:
        key = doc_field.source_name.lower()
        if key not in seen_names:
            merged.append(doc_field)
            seen_names.add(key)

    return merged
