"""Resolve a Braintrust project name to its id via the ``bt`` CLI.

The subprocess runner is injectable so this is unit-testable without the real
``bt`` binary or live auth.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from .errors import BtToolError, ProjectNotFoundError

# A runner takes argv and returns stdout text (raising on failure).
Runner = Callable[[list[str]], str]


def _default_runner(argv: list[str]) -> str:
    return subprocess.check_output(argv, text=True)


def resolve_project_id(name: str, *, runner: Runner | None = None) -> str:
    """Return the project id for ``name`` (reuses existing ``bt auth``)."""
    run = runner or _default_runner
    try:
        raw = run(["bt", "projects", "list", "--json"])
    except FileNotFoundError as exc:
        raise BtToolError(
            "`bt` CLI not found on PATH. Install it and run `bt auth login`."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise BtToolError(f"`bt projects list` failed: {exc}") from exc

    projects = json.loads(raw)
    for proj in projects:
        if proj.get("name") == name:
            return proj["id"]
    raise ProjectNotFoundError(name, [p.get("name", "") for p in projects])
