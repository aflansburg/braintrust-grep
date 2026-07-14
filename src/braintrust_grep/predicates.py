"""Local predicates applied to log rows after they're fetched.

BTQL can't do regex, and ``LIKE`` is blind to structured (JSON-object) fields,
so matching happens here in Python. Predicates are composable and each declares
which field paths it reads, so :func:`~braintrust_grep.search.search` can select
only those columns (never a full-row ``select: *``, which can be 20 MB/span).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# Sentinel distinguishing "key absent" from an empty value ("" / [] / {} / None).
MISSING: Any = object()

# Field path meaning "the entire row" (serialized to JSON for matching).
WHOLE_ROW = "*"

# Values treated as empty by EmptyOrMissing.
_EMPTY_VALUES: tuple[Any, ...] = (None, "", [], {})


@runtime_checkable
class Predicate(Protocol):
    def __call__(self, row: Mapping[str, Any]) -> bool: ...

    def field_paths(self) -> set[str]:
        """Dotted paths this predicate reads (``"*"`` means the whole row)."""
        ...


def extract(row: Mapping[str, Any], path: str) -> Any:
    """Return the value at a dotted ``path``, or :data:`MISSING` if absent."""
    if path in (WHOLE_ROW, "."):
        return row
    value: Any = row
    for part in path.split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            return MISSING
    return value


def as_text(value: Any) -> str:
    """Coerce a value to searchable text (empty string for MISSING)."""
    if value is MISSING:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def is_empty(value: Any) -> bool:
    """True if ``value`` is MISSING or an empty scalar/container."""
    return value is MISSING or value in _EMPTY_VALUES


@dataclass(frozen=True)
class Regex:
    """Match when ``pattern`` is found anywhere in ``field`` (as text)."""

    field: str
    pattern: str
    flags: int = 0

    def __post_init__(self):
        # compile eagerly to fail fast; store on the frozen instance
        object.__setattr__(self, "_re", re.compile(self.pattern, self.flags))

    def __call__(self, row: Mapping[str, Any]) -> bool:
        return self._re.search(as_text(extract(row, self.field))) is not None

    def field_paths(self) -> set[str]:
        return {self.field}


@dataclass(frozen=True)
class EmptyOrMissing:
    """Match when ``field`` is absent or its value is empty (``""``/``[]``/``{}``/null)."""

    field: str

    def __call__(self, row: Mapping[str, Any]) -> bool:
        return is_empty(extract(row, self.field))

    def field_paths(self) -> set[str]:
        return {self.field}


@dataclass(frozen=True)
class AllOf:
    predicates: tuple[Predicate, ...]

    def __init__(self, *predicates: Predicate):
        object.__setattr__(self, "predicates", tuple(predicates))

    def __call__(self, row: Mapping[str, Any]) -> bool:
        return all(p(row) for p in self.predicates)

    def field_paths(self) -> set[str]:
        return (
            set().union(*(p.field_paths() for p in self.predicates)) if self.predicates else set()
        )


@dataclass(frozen=True)
class AnyOf:
    predicates: tuple[Predicate, ...]

    def __init__(self, *predicates: Predicate):
        object.__setattr__(self, "predicates", tuple(predicates))

    def __call__(self, row: Mapping[str, Any]) -> bool:
        return any(p(row) for p in self.predicates)

    def field_paths(self) -> set[str]:
        return (
            set().union(*(p.field_paths() for p in self.predicates)) if self.predicates else set()
        )


@dataclass(frozen=True)
class Not:
    predicate: Predicate

    def __call__(self, row: Mapping[str, Any]) -> bool:
        return not self.predicate(row)

    def field_paths(self) -> set[str]:
        return self.predicate.field_paths()


def top_level_fields(paths: set[str]) -> set[str] | None:
    """Reduce dotted paths to their top-level column names.

    Returns ``None`` if any path is the whole row (caller must ``select: *``).
    """
    out: set[str] = set()
    for p in paths:
        if p in (WHOLE_ROW, "."):
            return None
        out.add(p.split(".")[0])
    return out
