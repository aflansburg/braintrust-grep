from __future__ import annotations

import pytest

from braintrust_grep.query import BtqlQuery, StructuredLikeWarning, WideWindowWarning


def test_render_basic():
    q = (
        BtqlQuery("pid")
        .created_between("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        .match("output", "evidence")
        .select(["id", "output"])
    )
    rendered = q.render(limit=100)
    assert "select: id, output" in rendered
    assert "from: project_logs('pid')" in rendered
    assert "created >= '2026-01-01T00:00:00Z'" in rendered
    assert "output MATCH 'evidence'" in rendered
    assert "limit: 100" in rendered


def test_render_with_cursor():
    q = BtqlQuery("pid").select(["id"])
    assert "cursor: 't1'" in q.render(limit=10, cursor="t1")


def test_render_without_select_raises():
    with pytest.raises(ValueError):
        BtqlQuery("pid").render(limit=10)


def test_like_on_structured_field_warns():
    with pytest.warns(StructuredLikeWarning):
        BtqlQuery("pid").where("output LIKE '%evidence%'")


def test_like_on_string_leaf_does_not_warn():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning -> error
        BtqlQuery("pid").where("metadata.model LIKE '%gpt%'")


def test_in_without_window_warns():
    with pytest.warns(WideWindowWarning):
        BtqlQuery("pid").in_("root_span_id", ["a", "b"])


def test_in_with_window_does_not_warn():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        q = BtqlQuery("pid").created_between("2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z")
        q.in_("root_span_id", ["a", "b"])


def test_quote_escapes_single_quotes():
    from braintrust_grep.query import quote

    assert quote("a'b") == "'a''b'"
