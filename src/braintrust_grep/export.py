"""Write matched/enriched rows to JSONL or CSV.

CSV columns are, by default, *derived from the rows* — the scalar top-level
fields present (including anything :func:`~braintrust_grep.enrich.enrich` added),
with ``created``/``span_id``/``root_span_id`` first and ``url`` last. Pass
explicit ``columns`` (``"header=path"`` or ``"path"``) to control the shape,
including nested paths like ``output`` or ``span_attributes.name``.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TextIO

from .links import span_deeplink
from .predicates import MISSING, as_text, extract

# Column = (header, dotted-path).
Column = tuple[str, str]

# Ordering hints for derived columns.
_CORE_FIRST = ("created", "span_id", "root_span_id")
_LAST = ("url",)


def parse_columns(specs: Sequence[str]) -> list[Column]:
    """Parse ``"header=path"`` / ``"path"`` specs (comma-splitting allowed)."""
    out: list[Column] = []
    for raw in specs:
        for spec in raw.split(","):
            spec = spec.strip()
            if not spec:
                continue
            if "=" in spec:
                header, path = spec.split("=", 1)
                out.append((header.strip(), path.strip()))
            else:
                out.append((spec.split(".")[-1], spec))
    return out


def derive_columns(rows: Sequence[dict[str, Any]]) -> list[Column]:
    """Infer a sensible CSV shape: scalar top-level keys, core first, url last."""
    keys: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key not in keys and not isinstance(value, (dict, list)):
                keys.append(key)
    ordered = [k for k in _CORE_FIRST if k in keys]
    ordered += [k for k in keys if k not in _CORE_FIRST and k not in _LAST]
    ordered += [k for k in _LAST if k in keys]
    return [(k, k) for k in ordered]


def add_urls(
    rows: Iterable[dict[str, Any]],
    *,
    org: str,
    project: str,
    project_id: str,
) -> list[dict[str, Any]]:
    """Set ``row['url']`` to a direct span deep-link (uses span_id, not id)."""
    out = []
    for row in rows:
        if row.get("span_id") and row.get("root_span_id"):
            row["url"] = span_deeplink(
                org, project, project_id, row["root_span_id"], row["span_id"]
            )
        out.append(row)
    return out


def to_jsonl(rows: Iterable[dict[str, Any]], out: TextIO | str | Path) -> int:
    fh, close = _open(out, "w")
    n = 0
    try:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            n += 1
    finally:
        if close:
            fh.close()
    return n


def to_csv(
    rows: Iterable[dict[str, Any]],
    out: TextIO | str | Path,
    columns: Sequence[Column] | None = None,
) -> int:
    rows = list(rows)
    cols = list(columns) if columns else derive_columns(rows)
    fh, close = _open(out, "w", newline="")
    n = 0
    try:
        writer = csv.writer(fh)
        writer.writerow([header for header, _ in cols])
        for row in rows:
            writer.writerow([_cell(row, path) for _, path in cols])
            n += 1
    finally:
        if close:
            fh.close()
    return n


def _cell(row: dict[str, Any], path: str) -> str:
    value = extract(row, path)
    return "" if value is MISSING else as_text(value)


def _open(out: TextIO | str | Path, mode: str, **kw):
    if isinstance(out, (str, Path)):
        return open(out, mode, encoding="utf-8", **kw), True
    return out, False
