"""Braintrust deep-link builder.

Important: a direct span link needs the span's ``span_id`` and its trace's
``root_span_id`` — NOT the row ``id`` (they differ). Using the row ``id`` for
``s=`` lands on the trace without selecting the right span.
"""

from __future__ import annotations

from urllib.parse import urlencode

_APP_BASE = "https://www.braintrust.dev/app"


def span_deeplink(
    org: str,
    project: str,
    project_id: str,
    root_span_id: str,
    span_id: str,
) -> str:
    """Build a URL that opens ``span_id`` inside its trace."""
    params = urlencode(
        {
            "object_type": "project_logs",
            "object_id": project_id,
            "r": root_span_id,
            "s": span_id,
            "tvt": "trace",
        }
    )
    return f"{_APP_BASE}/{org}/p/{project}/trace?{params}"
