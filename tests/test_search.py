from __future__ import annotations

import datetime as dt

from braintrust_grep.predicates import AllOf, EmptyOrMissing, Regex
from braintrust_grep.search import ROUTING_FIELDS, resolve_window, search
from conftest import json_response, make_client

FIXED_NOW = dt.datetime(2026, 7, 14, 12, 0, 0, tzinfo=dt.UTC)


def test_resolve_window_relative():
    lo, hi = resolve_window("14d", "now", now=lambda: FIXED_NOW)
    assert hi.startswith("2026-07-14T12:00:00")
    assert lo.startswith("2026-06-30T12:00:00")


def test_resolve_window_iso_and_epoch():
    lo, hi = resolve_window("2026-07-01T00:00:00Z", "2026-07-02T00:00:00Z")
    assert lo.startswith("2026-07-01T00:00:00")
    lo2, _ = resolve_window("1751328000000", "now", now=lambda: FIXED_NOW)
    assert lo2.startswith("2025-")  # epoch-ms parsed


def test_search_applies_predicate_and_autoselects_columns():
    rows_page = {
        "data": [
            {"id": 1, "output": {"symptoms": [1]}, "input": {"raw_text": "x"}},
            {"id": 2, "output": {"other": 1}, "input": {"raw_text": "y"}},
        ],
        "cursor": None,
    }
    client, _, rec = make_client([json_response(rows_page)])
    predicate = Regex("output", r'"symptoms"')
    matches = list(
        search(
            client,
            "pid",
            window=("2026-07-01T00:00:00Z", "2026-07-14T00:00:00Z"),
            predicate=predicate,
            match=[("output", "symptoms")],
        )
    )
    assert [m["id"] for m in matches] == [1]
    q = rec.bodies[0]["query"]
    assert "output MATCH 'symptoms'" in q
    # auto-select includes routing + predicate's top-level field, never `*`
    for col in (*ROUTING_FIELDS, "output"):
        assert col in q
    assert "select: *" not in q


def test_search_max_scan_and_extra_select():
    page = {
        "data": [{"id": 1, "output": {"symptoms": [1]}, "input": {"raw_text": ""}}],
        "cursor": None,
    }
    client, _, rec = make_client([json_response(page)])
    predicate = AllOf(Regex("output", r"symptoms"), EmptyOrMissing("input.raw_text"))
    matches = list(
        search(
            client,
            "pid",
            window=("2026-07-01T00:00:00Z", "2026-07-14T00:00:00Z"),
            predicate=predicate,
            extra_select=["span_attributes"],
            max_scan=5,
        )
    )
    assert len(matches) == 1
    assert "span_attributes" in rec.bodies[0]["query"]
