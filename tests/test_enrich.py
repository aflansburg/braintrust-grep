from __future__ import annotations

from braintrust_grep.enrich import enrich
from conftest import json_response, make_client


def test_enrich_joins_root_fields_by_root_span_id():
    matches = [
        {
            "id": "row1",
            "span_id": "s1",
            "root_span_id": "r1",
            "created": "2026-07-05T04:24:34.000Z",
        },
        {
            "id": "row2",
            "span_id": "s2",
            "root_span_id": "r2",
            "created": "2026-07-05T04:30:00.000Z",
        },
    ]
    # One bucket (same hour) -> one IN query. Root row is where span_id == root_span_id.
    page = {
        "data": [
            {"span_id": "r1", "root_span_id": "r1", "doc_id": "D1", "patient_id": "P1"},
            {"span_id": "child", "root_span_id": "r1", "doc_id": None, "patient_id": None},
            {"span_id": "r2", "root_span_id": "r2", "doc_id": "D2", "patient_id": "P2"},
        ],
        "cursor": None,
    }
    client, _, rec = make_client([json_response(page)])
    out = enrich(
        client,
        matches,
        project_id="pid",
        root_fields=["input.doc_id", "input.patient_id"],
        bucket="1h",
    )
    by_id = {r["id"]: r for r in out}
    assert by_id["row1"]["doc_id"] == "D1"
    assert by_id["row1"]["patient_id"] == "P1"
    assert by_id["row2"]["doc_id"] == "D2"
    # exactly one batched query, aliased + narrow window + IN
    q = rec.bodies[0]["query"]
    assert "input.doc_id as doc_id" in q
    assert "root_span_id IN (" in q
    assert "created >=" in q


def test_enrich_unresolved_roots_get_none():
    matches = [
        {
            "id": "x",
            "span_id": "s",
            "root_span_id": "missing",
            "created": "2026-07-05T04:24:34.000Z",
        }
    ]
    client, _, _ = make_client([json_response({"data": [], "cursor": None})])
    out = enrich(client, matches, project_id="pid", root_fields=["input.doc_id"])
    assert out[0]["doc_id"] is None
