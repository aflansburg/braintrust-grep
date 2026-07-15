"""Predicate for "a JSON object in a field has these keys empty-or-missing".

Nothing here is tied to a particular schema — you supply the ``field``, the
``keys`` to check, and (optionally) a text ``marker`` that precedes an embedded
JSON block. It handles three shapes of the field's value:

- already a dict/list (a structured column) — used directly;
- a JSON string — parsed;
- free text with an embedded JSON block after ``marker``, e.g.::

      === METADATA ===
      [ { "pages": [], "documentdata": null } ]

  (set ``marker="=== METADATA ==="``) — the block after the marker is parsed.

A row matches when *any* of the resulting objects has *every* key in ``keys``
empty-or-missing (absent, or ``""`` / ``[]`` / ``{}`` / ``null``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from .predicates import MISSING, extract, is_empty


@dataclass(frozen=True)
class MetadataObjectEmpty:
    field: str
    keys: tuple[str, ...]
    marker: str | None = None
    require_marker: bool = True

    def __call__(self, row: Mapping[str, object]) -> bool:
        objects = self._objects(extract(row, self.field))
        if not objects:
            return False
        return any(
            isinstance(obj, Mapping) and all(is_empty(obj.get(k, MISSING)) for k in self.keys)
            for obj in objects
        )

    def _objects(self, value: object) -> list | None:
        if value is MISSING:
            return None
        if isinstance(value, Mapping):
            return [value]
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return None
        text = value
        if self.marker:
            idx = text.find(self.marker)
            if idx < 0:
                if self.require_marker:
                    return None
            else:
                text = text[idx + len(self.marker) :]
        return _decode_json_block(text)

    def field_paths(self) -> set[str]:
        return {self.field}


def _decode_json_block(text: str) -> list | None:
    """Decode the first JSON array/object appearing in ``text``."""
    candidates = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not candidates:
        return None
    start = min(candidates)
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    if isinstance(obj, list):
        return obj
    if isinstance(obj, Mapping):
        return [obj]
    return None
