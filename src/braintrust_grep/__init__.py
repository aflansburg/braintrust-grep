"""braintrust-grep: regex & structural search over Braintrust logs.

BTQL has no regex, and its ``LIKE`` is blind to structured fields — so pull logs
with a fast server-side prefilter (``created`` window + ``MATCH``) and match
locally. All the hard-won correctness (30s timeout, rate limit, redirect+gzip,
row-id≠span_id, span links) is baked into :class:`BtqlClient`.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .client import BtqlClient
from .config import ClientOptions
from .enrich import enrich
from .errors import (
    AuthError,
    BtgrepError,
    BtqlHttpError,
    BtToolError,
    ProjectNotFoundError,
    QueryTimeoutError,
    RateLimitError,
)
from .links import span_deeplink
from .metadata import MetadataObjectEmpty
from .predicates import (
    MISSING,
    AllOf,
    AnyOf,
    EmptyOrMissing,
    Not,
    Predicate,
    Regex,
    as_text,
    extract,
    is_empty,
)
from .projects import resolve_project_id
from .query import BtqlQuery, StructuredLikeWarning, WideWindowWarning
from .search import resolve_window, search

__all__ = [
    "__version__",
    "BtqlClient",
    "ClientOptions",
    "BtqlQuery",
    "StructuredLikeWarning",
    "WideWindowWarning",
    "search",
    "resolve_window",
    "enrich",
    "span_deeplink",
    "resolve_project_id",
    # predicates
    "Predicate",
    "Regex",
    "EmptyOrMissing",
    "MetadataObjectEmpty",
    "AllOf",
    "AnyOf",
    "Not",
    "extract",
    "as_text",
    "is_empty",
    "MISSING",
    # errors
    "BtgrepError",
    "AuthError",
    "ProjectNotFoundError",
    "BtToolError",
    "BtqlHttpError",
    "RateLimitError",
    "QueryTimeoutError",
]
