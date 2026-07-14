"""A small BTQL query builder that encodes the fast-path guardrails.

Reliable, under-30s queries use ``created``-range + ``MATCH`` + cursor
pagination. This builder steers callers there: it emits explicit ``created``
bounds, prefers ``MATCH``, warns when a ``LIKE`` targets a structured field
(where it silently matches nothing), refuses a silent ``select: *``, and warns
when an ``IN (...)`` is used without a narrow time window.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

# Top-level columns that are structured (JSON objects) on Braintrust logs, where
# `LIKE` does not coerce to text and returns nothing.
_STRUCTURED_ROOTS = {"output", "input", "metadata", "expected", "scores", "metrics"}
_LIKE_RE = re.compile(r"([A-Za-z_][\w.]*)\s+(?:I?LIKE)\b", re.IGNORECASE)


class StructuredLikeWarning(UserWarning):
    """A ``LIKE`` targets a structured field and will likely match nothing."""


class WideWindowWarning(UserWarning):
    """An ``IN (...)`` filter is used over a wide/unspecified time window."""


def quote(value: str) -> str:
    """Quote a BTQL string literal (SQL-style single-quote doubling)."""
    return "'" + str(value).replace("'", "''") + "'"


@dataclass
class BtqlQuery:
    project_id: str
    _filters: list[str] = field(default_factory=list)
    _select: list[str] = field(default_factory=list)
    _order: str | None = None
    _has_in: bool = False
    _has_window: bool = False

    # -- filters ----------------------------------------------------------
    def created_between(self, lo: str, hi: str) -> BtqlQuery:
        self._filters.append(f"created >= {quote(lo)} AND created <= {quote(hi)}")
        self._has_window = True
        return self

    def match(self, field_name: str, text: str) -> BtqlQuery:
        """Server-side full-text match (works on structured fields, unlike LIKE)."""
        self._filters.append(f"{field_name} MATCH {quote(text)}")
        return self

    def where(self, expr: str) -> BtqlQuery:
        """Add a raw BTQL filter expression (advanced). Warns on structured LIKE."""
        _warn_structured_like(expr)
        self._filters.append(expr)
        return self

    def in_(self, field_name: str, values) -> BtqlQuery:
        """Add ``field IN (...)``. Must be paired with a narrow ``created`` window."""
        vals = ", ".join(quote(v) for v in values)
        self._filters.append(f"{field_name} IN ({vals})")
        self._has_in = True
        if not self._has_window:
            warnings.warn(
                "IN (...) without a created window will scan the whole project and "
                "likely exceed the 30s timeout; add created_between() first.",
                WideWindowWarning,
                stacklevel=2,
            )
        return self

    # -- projection / ordering -------------------------------------------
    def select(self, fields: list[str]) -> BtqlQuery:
        """Set the select list (column names or ``expr as alias`` strings)."""
        self._select = list(fields)
        return self

    def select_all(self) -> BtqlQuery:
        """Explicitly select ``*`` (opt-in; can pull up to 20 MB/span)."""
        warnings.warn(
            "select_all() pulls every field including large raw_text; prefer select([...]).",
            UserWarning,
            stacklevel=2,
        )
        self._select = ["*"]
        return self

    def order_by(self, expr: str) -> BtqlQuery:
        self._order = expr
        return self

    # -- render -----------------------------------------------------------
    def render(self, *, limit: int, cursor: str | None = None) -> str:
        if not self._select:
            raise ValueError("no select set; call .select([...]) or .select_all()")
        clauses = [
            f"select: {', '.join(self._select)}",
            f"from: project_logs('{self.project_id}')",
        ]
        if self._filters:
            clauses.append(f"filter: {' AND '.join(self._filters)}")
        if self._order:
            clauses.append(f"sort: {self._order}")
        clauses.append(f"limit: {limit}")
        if cursor:
            clauses.append(f"cursor: {quote(cursor)}")
        return " | ".join(clauses)


def _warn_structured_like(expr: str) -> None:
    for match in _LIKE_RE.finditer(expr):
        field_path = match.group(1)
        root = field_path.split(".")[0]
        # Warn when targeting a structured root with no string leaf (e.g. `output`,
        # but not `metadata.model` which resolves to a string).
        if root in _STRUCTURED_ROOTS and "." not in field_path:
            warnings.warn(
                f"LIKE on structured field {field_path!r} matches nothing when the "
                f"field is a JSON object; use MATCH instead.",
                StructuredLikeWarning,
                stacklevel=3,
            )
