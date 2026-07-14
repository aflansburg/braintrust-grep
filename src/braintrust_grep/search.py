"""Scan a project + time window and yield rows passing a local predicate.

Server-side we apply only fast, index-friendly prefilters (``created`` range +
``MATCH``); the regex / structural matching happens locally on each row.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from .client import BtqlClient
from .predicates import Predicate, top_level_fields
from .query import BtqlQuery

# Columns always selected so downstream enrich/export/links have what they need.
ROUTING_FIELDS = ("id", "created", "span_id", "root_span_id")

_REL_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def resolve_window(
    since: str,
    until: str | None = None,
    *,
    now: Callable[[], _dt.datetime] | None = None,
) -> tuple[str, str]:
    """Resolve ``since``/``until`` to explicit ISO-8601 UTC bounds ``(lo, hi)``.

    Accepts relative durations (``14d``, ``36h``), ISO-8601 timestamps, or
    epoch-milliseconds. ``now`` is injectable for deterministic tests.
    """
    now_fn = now or (lambda: _dt.datetime.now(_dt.UTC))
    hi_dt = _parse_instant(until, now_fn) if until and until != "now" else now_fn()
    lo_dt = _parse_instant(since, now_fn, reference=hi_dt)
    return _iso(lo_dt), _iso(hi_dt)


def search(
    client: BtqlClient,
    project_id: str,
    *,
    window: tuple[str, str],
    predicate: Predicate,
    match: Sequence[tuple[str, str]] = (),
    where: Sequence[str] = (),
    select: Sequence[str] | None = None,
    extra_select: Sequence[str] = (),
    max_scan: int | None = None,
    max_matches: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield rows in ``window`` that satisfy ``predicate``.

    ``match`` entries become server-side ``field MATCH 'text'`` prefilters (the
    reliable way to narrow structured fields). ``select`` overrides the
    auto-derived column list; ``extra_select`` adds to it.
    """
    lo, hi = window
    query = BtqlQuery(project_id).created_between(lo, hi)
    for field_name, text in match:
        query.match(field_name, text)
    for expr in where:
        query.where(expr)

    if select is not None:
        query.select(list(select))
    else:
        columns = top_level_fields(predicate.field_paths())
        if columns is None:
            query.select_all()
        else:
            query.select(sorted(set(columns) | set(ROUTING_FIELDS) | set(extra_select)))

    matched = 0
    for row in client.paginate(query, max_rows=max_scan):
        if predicate(row):
            matched += 1
            yield row
            if max_matches is not None and matched >= max_matches:
                return


def _parse_instant(
    value: str,
    now_fn: Callable[[], _dt.datetime],
    *,
    reference: _dt.datetime | None = None,
) -> _dt.datetime:
    rel = _REL_RE.match(value)
    if rel:
        seconds = int(rel.group(1)) * _UNIT_SECONDS[rel.group(2).lower()]
        base = reference or now_fn()
        return base - _dt.timedelta(seconds=seconds)
    if value.isdigit():  # epoch milliseconds
        return _dt.datetime.fromtimestamp(int(value) / 1000, _dt.UTC)
    iso = value.replace("Z", "+00:00")
    dt = _dt.datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.UTC)


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
