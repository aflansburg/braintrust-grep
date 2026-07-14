from __future__ import annotations

import subprocess

import pytest

from braintrust_grep.errors import BtToolError, ProjectNotFoundError
from braintrust_grep.projects import resolve_project_id

CANNED = '[{"id":"abc","name":"alpha"},{"id":"xyz","name":"beta"}]'


def test_resolve_by_name():
    assert resolve_project_id("beta", runner=lambda argv: CANNED) == "xyz"


def test_not_found_lists_available():
    with pytest.raises(ProjectNotFoundError) as exc:
        resolve_project_id("gamma", runner=lambda argv: CANNED)
    assert "alpha" in str(exc.value) and "beta" in str(exc.value)


def test_bt_missing():
    def boom(argv):
        raise FileNotFoundError("bt")

    with pytest.raises(BtToolError):
        resolve_project_id("beta", runner=boom)


def test_bt_failure():
    def boom(argv):
        raise subprocess.CalledProcessError(1, argv)

    with pytest.raises(BtToolError):
        resolve_project_id("beta", runner=boom)
