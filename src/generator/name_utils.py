"""Client name sanitization for generated Python identifiers."""

from __future__ import annotations

import re


def sanitize_client_name(client_name: str) -> tuple[str, str, str, str]:
    """Return class_name, module_name, file_stem, and display name from client_name.

    Examples:
        "Guidewire Carrier A" -> GuidewireCarrierAAdapter, guidewire_carrier_a_adapter, ...
        "carrier-#1" -> Carrier1Adapter, carrier_1_adapter, ...
    """
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-_]", "", client_name)
    parts = re.split(r"[\s\-_]+", cleaned.strip())
    words = [p for p in parts if p]
    if not words:
        words = ["Client"]
    pascal = "".join(word[:1].upper() + word[1:] for word in words)
    snake = "_".join(word.lower() for word in words)
    class_name = f"{pascal}Adapter"
    file_stem = f"{snake}_adapter"
    module_name = file_stem
    return class_name, module_name, file_stem, client_name.strip() or "Client"
