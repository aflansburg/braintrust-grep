from __future__ import annotations

from braintrust_grep.metadata import MetadataObjectEmpty

EMPTY_META = '{"documentclass": "X", "pages": [], "status": "CLOSED"}'
EMPTY_DOC = {"input": {"raw_text": f"=== METADATA ===\n[{EMPTY_META}]\nsome trailing text"}}
FULL_DOC = {
    "input": {"raw_text": '=== METADATA ===\n[{"pages": [{"pageid": "1"}], "documentdata": "abc"}]'}
}
HAS_DOCDATA = {"input": {"raw_text": '=== METADATA ===\n[{"pages": [], "documentdata": "abc"}]'}}


def test_matches_empty_pages_and_missing_documentdata():
    # pages == [] (empty) and documentdata absent -> both empty-or-missing
    assert MetadataObjectEmpty()(EMPTY_DOC)


def test_does_not_match_when_pages_populated():
    assert not MetadataObjectEmpty()(FULL_DOC)


def test_does_not_match_when_documentdata_present():
    assert not MetadataObjectEmpty()(HAS_DOCDATA)


def test_no_metadata_block_is_no_match():
    assert not MetadataObjectEmpty()({"input": {"raw_text": "no marker here"}})
    assert not MetadataObjectEmpty()({"input": {"raw_text": 123}})  # non-string


def test_custom_keys():
    row = {"input": {"raw_text": '=== METADATA ===\n[{"a": [], "b": null, "c": "x"}]'}}
    assert MetadataObjectEmpty(keys=("a", "b"))(row)  # both empty
    assert not MetadataObjectEmpty(keys=("a", "c"))(row)  # c is populated
