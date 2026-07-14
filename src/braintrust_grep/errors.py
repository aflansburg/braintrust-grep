"""Exception hierarchy for braintrust-grep.

The library never calls ``sys.exit``; it raises these. Only the CLI layer
translates them into process exits.
"""

from __future__ import annotations


class BtgrepError(Exception):
    """Base class for all braintrust-grep errors."""


class AuthError(BtgrepError):
    """No/invalid Braintrust API key available."""


class ProjectNotFoundError(BtgrepError):
    """A project name could not be resolved to an id."""

    def __init__(self, name: str, available: list[str] | None = None):
        self.name = name
        self.available = available or []
        msg = f"project {name!r} not found"
        if self.available:
            msg += f". Available: {', '.join(sorted(self.available))}"
        super().__init__(msg)


class BtToolError(BtgrepError):
    """The `bt` CLI is missing or failed while resolving a project."""


class BtqlHttpError(BtgrepError):
    """A BTQL request failed with a non-retryable status, or exhausted retries."""

    def __init__(self, status: int, body: str, *, hint: str | None = None):
        self.status = status
        self.body = body
        self.hint = hint
        msg = f"BTQL request failed ({status}): {body}"
        if hint:
            msg += f"\nhint: {hint}"
        super().__init__(msg)


class RateLimitError(BtqlHttpError):
    """Hit the org BTQL rate limit (HTTP 429) and could not recover.

    Braintrust enforces ~20 BTQL requests / 60s per org. Increase
    ``ClientOptions.min_request_interval`` or reduce concurrency.
    """


class QueryTimeoutError(BtqlHttpError):
    """A single query exceeded Braintrust's 30s server timeout (HTTP 504).

    Almost always caused by scanning too much: narrow the ``created`` window,
    prefer ``MATCH`` + cursor pagination, and avoid ``IN (...)``/``LIKE`` over
    wide windows.
    """
