from __future__ import annotations

import csv
import io

from braintrust_grep.export import (
    add_urls,
    derive_columns,
    parse_columns,
    to_csv,
    to_jsonl,
)


def test_parse_columns_headers_and_commas():
    cols = parse_columns(["created", "name=span_attributes.name", "a,b"])
    assert cols == [
        ("created", "created"),
        ("name", "span_attributes.name"),
        ("a", "a"),
        ("b", "b"),
    ]


def test_derive_columns_scalars_only_core_first_url_last():
    rows = [
        {
            "created": "t",
            "span_id": "s",
            "root_span_id": "r",
            "doc_id": "D",
            "output": {"x": 1},
            "url": "u",
        },
    ]
    cols = derive_columns(rows)
    headers = [h for h, _ in cols]
    assert headers == ["created", "span_id", "root_span_id", "doc_id", "url"]
    assert "output" not in headers  # nested value excluded from auto columns


def test_to_csv_auto_columns():
    rows = [{"created": "t", "span_id": "s", "root_span_id": "r", "doc_id": "D1"}]
    buf = io.StringIO()
    n = to_csv(rows, buf)
    assert n == 1
    parsed = list(csv.reader(io.StringIO(buf.getvalue())))
    assert parsed[0] == ["created", "span_id", "root_span_id", "doc_id"]
    assert parsed[1] == ["t", "s", "r", "D1"]


def test_to_csv_explicit_columns_with_nested_path():
    rows = [{"span_id": "s", "output": {"symptoms": [1]}}]
    buf = io.StringIO()
    to_csv(rows, buf, parse_columns(["span_id", "sym=output.symptoms"]))
    parsed = list(csv.reader(io.StringIO(buf.getvalue())))
    assert parsed[0] == ["span_id", "sym"]
    assert parsed[1] == ["s", "[1]"]  # non-string serialized to JSON


def test_add_urls_uses_span_and_root():
    rows = add_urls(
        [{"span_id": "S", "root_span_id": "R"}],
        org="Org",
        project="proj",
        project_id="PID",
    )
    assert "r=R" in rows[0]["url"] and "s=S" in rows[0]["url"]


def test_to_jsonl_roundtrip():
    buf = io.StringIO()
    n = to_jsonl([{"a": 1}, {"b": 2}], buf)
    assert n == 2
    assert buf.getvalue().splitlines() == ['{"a": 1}', '{"b": 2}']
