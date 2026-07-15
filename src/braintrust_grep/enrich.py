"""Join matched spans to fields on other spans of the same trace.

The classic use: pull ``doc_id``/``patient_id``/… from the root
"Document Processing" span. We can't fetch those per-row over a wide window
(``root_span_id IN`` over 14 days blows the 30s timeout), so we bucket matches
into narrow ``created`` windows and batch ``root_span_id IN (...)`` within each.

The root span is the row where ``span_id == root_span_id`` (NOT ``id``).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Sequence
from typing import Any

from .client import BtqlClient
from .query import BtqlQuery

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _leaf(path: str) -> str:
    return path.split(".")[-1]


def _parse_bucket(spec: str) -> int:
    num, unit = spec[:-1], spec[-1].lower()
    return int(num) * _UNIT_SECONDS[unit]


def _floor(dt: _dt.datetime, seconds: int) -> _dt.datetime:
    epoch = int(dt.timestamp())
    return _dt.datetime.fromtimestamp(epoch - (epoch % seconds), _dt.UTC)


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def enrich(
    client: BtqlClient,
    rows: Sequence[dict[str, Any]],
    *,
    project_id: str,
    root_fields: Sequence[str],
    bucket: str = "1h",
    batch: int = 60,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Return ``rows`` with each root field flattened onto matching rows.

    ``root_fields`` are dotted paths on the root span (e.g. ``input.doc_id``);
    the flattened key on each row is the leaf name (``doc_id``).
    """
    rows = list(rows)
    bucket_seconds = _parse_bucket(bucket)
    aliases = [f"{p} as {_leaf(p)}" for p in root_fields]
    leaves = [_leaf(p) for p in root_fields]

    # group root_span_ids by created-hour bucket
    buckets: dict[_dt.datetime, set[str]] = {}
    for row in rows:
        root = row.get("root_span_id")
        created = row.get("created")
        if not root or not created:
            continue
        key = _floor(_parse_created(created), bucket_seconds)
        buckets.setdefault(key, set()).add(root)

    root_map: dict[str, dict[str, Any]] = {}
    total_queries = sum((len(roots) + batch - 1) // batch for roots in buckets.values())
    done = 0
    for start, roots in sorted(buckets.items()):
        lo = _iso(start - _dt.timedelta(hours=1))
        hi = _iso(start + _dt.timedelta(seconds=bucket_seconds) + _dt.timedelta(minutes=5))
        root_list = sorted(roots)
        for k in range(0, len(root_list), batch):
            chunk = root_list[k : k + batch]
            query = (
                BtqlQuery(project_id)
                .created_between(lo, hi)
                .in_("root_span_id", chunk)
                .select(["span_id", "root_span_id", *aliases])
            )
            for r in client.paginate(query):
                if r.get("span_id") == r.get("root_span_id"):
                    root_map[r["root_span_id"]] = {leaf: r.get(leaf) for leaf in leaves}
            done += 1
            if progress:
                progress(f"enrich: {done}/{total_queries} queries · {len(root_map)} roots resolved")

    for row in rows:
        fields = root_map.get(row.get("root_span_id", ""), {})
        for leaf in leaves:
            row[leaf] = fields.get(leaf)
    return rows


def _parse_created(value: str) -> _dt.datetime:
    dt = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.UTC)
