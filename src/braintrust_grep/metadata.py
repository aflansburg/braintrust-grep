"""Structural predicate for the ``=== METADATA ===`` block embedded in text.

Some pipelines prepend a metadata JSON array to a document's ``raw_text``:

    === METADATA ===
    [ { "documentclass": "...", "pages": [], ... } ]

This predicate parses that JSON and matches when *every* named key on *any*
metadata object is empty-or-missing — e.g. an "empty document" with no
``pages`` and no ``documentdata``. Parsing the JSON is far more robust than
trying to express "key missing or empty" as a regex.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from .predicates import extract, is_empty

_MARKER = "=== METADATA ==="


@dataclass(frozen=True)
class MetadataObjectEmpty:
    field: str = "input.raw_text"
    keys: tuple[str, ...] = ("pages", "documentdata")

    def __call__(self, row: Mapping[str, object]) -> bool:
        value = extract(row, self.field)
        text = value if isinstance(value, str) else None
        if text is None:
            return False
        objects = _parse_metadata(text)
        if objects is None:
            return False
        return any(
            isinstance(obj, Mapping) and all(is_empty(obj.get(k, _ABSENT)) for k in self.keys)
            for obj in objects
        )

    def field_paths(self) -> set[str]:
        return {self.field}


# Distinct absent-marker so obj.get(k, _ABSENT) reports missing keys as empty.
_ABSENT: object = None  # None is already treated as empty by is_empty


def _parse_metadata(text: str) -> list | None:
    """Extract and JSON-decode the array following the METADATA marker."""
    start = text.find(_MARKER)
    if start < 0:
        start = text.find("METADATA")
        if start < 0:
            return None
    bracket = text.find("[", start)
    if bracket < 0:
        return None
    try:
        arr, _ = json.JSONDecoder().raw_decode(text[bracket:])
    except ValueError:
        return None
    if isinstance(arr, list):
        return arr
    return [arr]
