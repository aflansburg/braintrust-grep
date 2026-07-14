from __future__ import annotations

import re

from braintrust_grep.predicates import (
    MISSING,
    AllOf,
    AnyOf,
    EmptyOrMissing,
    Not,
    Regex,
    as_text,
    extract,
    is_empty,
    top_level_fields,
)


def test_extract_dotted_and_missing():
    row = {"input": {"raw_text": "hi", "meta": {"n": 1}}}
    assert extract(row, "input.raw_text") == "hi"
    assert extract(row, "input.meta.n") == 1
    assert extract(row, "input.nope") is MISSING
    assert extract(row, "input.raw_text.deeper") is MISSING


def test_as_text_serializes_non_strings():
    assert as_text("x") == "x"
    assert as_text(MISSING) == ""
    assert as_text({"a": 1}) == '{"a": 1}'


def test_is_empty_matrix():
    for empty in (MISSING, None, "", [], {}):
        assert is_empty(empty)
    for full in ("x", [1], {"a": 1}, 0, False):
        assert not is_empty(full)


def test_regex_matches_structured_field_via_json_text():
    # The bug that caused the 650x undercount: `output` is a dict. A local regex
    # sees the serialized JSON, so it matches where a server-side LIKE would not.
    row = {"output": {"symptoms": [{"evidence": "x"}]}}
    assert Regex("output", r'"symptoms"\s*:\s*\[')(row)
    assert not Regex("output", r'"nope"')(row)


def test_regex_ignorecase():
    row = {"a": "HELLO"}
    assert Regex("a", "hello", re.IGNORECASE)(row)
    assert not Regex("a", "hello")(row)


def test_empty_or_missing():
    assert EmptyOrMissing("x")({"x": []})
    assert EmptyOrMissing("x")({})  # missing
    assert not EmptyOrMissing("x")({"x": [1]})


def test_allof_anyof_not():
    row = {"a": "1", "b": ""}
    assert AllOf(Regex("a", "1"), EmptyOrMissing("b"))(row)
    assert not AllOf(Regex("a", "1"), Regex("b", "x"))(row)
    assert AnyOf(Regex("a", "zzz"), EmptyOrMissing("b"))(row)
    assert Not(Regex("a", "zzz"))(row)


def test_field_paths_and_top_level():
    p = AllOf(Regex("input.raw_text", "x"), EmptyOrMissing("output"))
    assert p.field_paths() == {"input.raw_text", "output"}
    assert top_level_fields(p.field_paths()) == {"input", "output"}
    assert top_level_fields({"*"}) is None
