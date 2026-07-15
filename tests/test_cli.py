from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from braintrust_grep import cli
from conftest import json_response, make_client

runner = CliRunner()


def test_version():
    result = runner.invoke(cli.app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_read_pattern_from_file(tmp_path):
    p = tmp_path / "pat.re"
    p.write_text(r'"symptoms"\s*:\s*\[' + "\n")
    assert cli._read_pattern(f"@{p}") == r'"symptoms"\s*:\s*\['
    assert cli._read_pattern("literal") == "literal"


def test_build_predicate_requires_something(capsys):
    # No predicates -> exits with a helpful message on stderr (captured, not leaked).
    with pytest.raises(typer.Exit):
        cli._build_predicate([], [], [], any_mode=False, ignore_case=False)
    assert "at least one --regex" in capsys.readouterr().err


def test_search_command_streams_jsonl(monkeypatch):
    page = {
        "data": [
            {
                "id": 1,
                "span_id": "s1",
                "root_span_id": "r1",
                "created": "t",
                "output": {"symptoms": [1]},
            },
            {"id": 2, "span_id": "s2", "root_span_id": "r2", "created": "t", "output": {}},
        ],
        "cursor": None,
    }
    client, _, _ = make_client([json_response(page)])
    monkeypatch.setattr(cli, "_client", lambda: client)

    result = runner.invoke(
        cli.app,
        [
            "search",
            "--project-id",
            "pid",
            "--match-fulltext",
            "output=symptoms",
            "--regex",
            r"output=symptoms",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert [row["id"] for row in lines] == [1]


def test_load_spec_json(tmp_path):
    spec = {"project": "p", "since": "7d"}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(spec))
    assert cli._load_spec(str(f)) == spec


def test_load_spec_yaml(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("project: p\nsince: 7d\n")
    loaded = cli._load_spec(str(f))
    assert loaded["project"] == "p" and loaded["since"] == "7d"


def test_build_metadata_string_with_marker():
    # CLI string form "FIELD:keys" + a shared --metadata-marker
    preds = cli._build_metadata(["input.raw_text:pages,documentdata"], "=== METADATA ===")
    assert len(preds) == 1
    p = preds[0]
    assert p.field == "input.raw_text"
    assert p.keys == ("pages", "documentdata")
    assert p.marker == "=== METADATA ===" and p.require_marker is True
    # and it actually matches an empty-doc row
    row = {"input": {"raw_text": '=== METADATA ===\n[{"pages": [], "status": "X"}]'}}
    assert p(row)


def test_build_metadata_string_requires_keys():
    with pytest.raises(typer.Exit):
        cli._build_metadata(["input.raw_text"], None)  # no ':' -> error


def test_build_metadata_spec_dict_carries_own_marker():
    preds = cli._build_metadata(
        [{"field": "m", "keys": ["a", "b"], "marker": "@@", "require_marker": False}], None
    )
    p = preds[0]
    assert p.field == "m" and p.keys == ("a", "b")
    assert p.marker == "@@" and p.require_marker is False
