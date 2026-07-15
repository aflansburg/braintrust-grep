from __future__ import annotations

from braintrust_grep.metadata import MetadataObjectEmpty

MARKER = "=== METADATA ==="


def _doc(meta: str) -> dict:
    return {"input": {"raw_text": f"{MARKER}\n[{meta}]\ntrailing text"}}


EMPTY_DOC = _doc('{"documentclass": "X", "pages": [], "status": "CLOSED"}')
FULL_DOC = _doc('{"pages": [{"pageid": "1"}], "documentdata": "abc"}')
HAS_DOCDATA = _doc('{"pages": [], "documentdata": "abc"}')


def _pred(**kw):
    return MetadataObjectEmpty("input.raw_text", ("pages", "documentdata"), marker=MARKER, **kw)


def test_marker_empty_pages_and_missing_documentdata_matches():
    assert _pred()(EMPTY_DOC)


def test_populated_pages_does_not_match():
    assert not _pred()(FULL_DOC)


def test_present_documentdata_does_not_match():
    assert not _pred()(HAS_DOCDATA)


def test_marker_absent_with_require_marker_is_no_match():
    row = {"input": {"raw_text": '[{"pages": [], "documentdata": null}] (no marker here)'}}
    assert not _pred()(row)  # require_marker=True by default
    assert _pred(require_marker=False)(row)  # …but parses when not required


def test_structured_dict_field_no_marker():
    # field is already a JSON object -> no marker needed
    row = {"meta": {"pages": [], "documentdata": None}}
    assert MetadataObjectEmpty("meta", ("pages", "documentdata"))(row)
    row2 = {"meta": {"pages": [1], "documentdata": None}}
    assert not MetadataObjectEmpty("meta", ("pages", "documentdata"))(row2)


def test_json_string_field_no_marker():
    row = {"payload": '[{"pages": [], "documentdata": ""}]'}
    assert MetadataObjectEmpty("payload", ("pages", "documentdata"))(row)


def test_non_string_non_json_field_is_no_match():
    assert not _pred()({"input": {"raw_text": 123}})
    assert not _pred()({"input": {}})  # field missing


def test_custom_keys():
    row = {"m": {"a": [], "b": None, "c": "x"}}
    assert MetadataObjectEmpty("m", ("a", "b"))(row)  # both empty
    assert not MetadataObjectEmpty("m", ("a", "c"))(row)  # c is populated
