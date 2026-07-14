"""Client behavior: pacing, retry/backoff, redirect+gzip, pagination, errors."""

from __future__ import annotations

import pytest

from braintrust_grep.errors import QueryTimeoutError, RateLimitError
from braintrust_grep.query import BtqlQuery
from conftest import (
    error_response,
    gzip_response,
    json_response,
    make_client,
    redirect_response,
)


def test_pacing_inserts_min_interval_between_requests():
    client, clock, _ = make_client(
        [json_response({"data": []}), json_response({"data": []})],
        min_request_interval=3.4,
    )
    client.query("q1")
    client.query("q2")
    assert clock.sleeps == [pytest.approx(3.4)]  # one paced gap before the 2nd


def test_retries_408_then_504_then_succeeds():
    client, clock, rec = make_client(
        [error_response(408), error_response(504), json_response({"data": [{"id": 1}]})],
        max_retries=6,
    )
    body = client.query("q")
    assert body == {"data": [{"id": 1}]}
    assert len(rec.requests) == 3  # two retries
    assert clock.sleeps, "expected backoff sleeps"


def test_exhausting_retries_on_504_raises_query_timeout():
    client, _, _ = make_client([error_response(504), error_response(504)], max_retries=2)
    with pytest.raises(QueryTimeoutError) as exc:
        client.query("q")
    assert "30s" in str(exc.value)


def test_429_raises_rate_limit_error():
    client, _, _ = make_client([error_response(429), error_response(429)], max_retries=2)
    with pytest.raises(RateLimitError):
        client.query("q")


def test_retry_after_header_is_honored():
    client, clock, _ = make_client(
        [error_response(429, {"Retry-After": "5"}), json_response({"data": []})],
        max_retries=3,
    )
    client.query("q")
    assert 5.0 in clock.sleeps


def test_follows_redirect_and_gunzips():
    client, _, _ = make_client([redirect_response(), gzip_response({"data": [{"id": 7}]})])
    body = client.query("q")
    assert body == {"data": [{"id": 7}]}


def test_direct_gzip_body_is_decoded():
    client, _, _ = make_client([gzip_response({"data": [{"id": 9}]})])
    assert client.query("q") == {"data": [{"id": 9}]}


def test_paginate_follows_cursor_and_passes_it_back():
    client, _, rec = make_client(
        [
            json_response({"data": [{"id": 1}], "cursor": "t1"}),
            json_response({"data": [{"id": 2}], "cursor": None}),
        ]
    )
    query = (
        BtqlQuery("proj")
        .created_between("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        .select(["id"])
    )
    rows = list(client.paginate(query))
    assert [r["id"] for r in rows] == [1, 2]
    assert "cursor: 't1'" in rec.bodies[1]["query"]  # 2nd request carried the cursor


def test_paginate_respects_max_rows():
    client, _, rec = make_client(
        [json_response({"data": [{"id": 1}, {"id": 2}, {"id": 3}], "cursor": "t1"})]
    )
    query = (
        BtqlQuery("proj")
        .created_between("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        .select(["id"])
    )
    rows = list(client.paginate(query, max_rows=2))
    assert len(rows) == 2
    assert len(rec.requests) == 1  # stopped mid-page, no second fetch
