"""Client configuration and environment resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from .errors import AuthError

DEFAULT_BASE_URL = "https://api.braintrust.dev/btql"

# Retryable HTTP statuses. 408 (request timeout) and 504 (gateway timeout) are
# the PRIMARY failure modes when a query brushes the 30s server limit, so they
# must be here — the original throwaway script omitted them.
DEFAULT_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ClientOptions:
    """Tunable knobs for :class:`~braintrust_grep.client.BtqlClient`.

    Defaults are chosen to stay within Braintrust's limits:
    ~20 BTQL requests / 60s per org (hence ``min_request_interval`` ~3.4s)
    and a 30s per-query server timeout.
    """

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    org: str | None = None
    min_request_interval: float = 3.4
    request_timeout: float = 180.0
    max_retries: int = 6
    page_size: int = 1000
    retry_statuses: frozenset[int] = field(default_factory=lambda: DEFAULT_RETRY_STATUSES)
    backoff_base: float = 2.0
    backoff_cap: float = 60.0
    follow_redirects: bool = True

    @classmethod
    def from_env(cls, **overrides) -> ClientOptions:
        """Build options from environment variables.

        Reads ``BRAINTRUST_API_KEY`` (required), ``BRAINTRUST_BTQL_URL`` and
        ``BRAINTRUST_ORG_NAME`` (optional). If ``python-dotenv`` is installed
        and a ``.env`` exists, it is loaded first as a convenience — but env
        vars already set always win, and ``.env`` is never required.
        """
        _maybe_load_dotenv()
        api_key = overrides.pop("api_key", None) or os.environ.get("BRAINTRUST_API_KEY")
        if not api_key:
            raise AuthError("BRAINTRUST_API_KEY is not set (env, .env, or api_key= argument).")
        opts = cls(
            api_key=api_key,
            base_url=os.environ.get("BRAINTRUST_BTQL_URL", DEFAULT_BASE_URL),
            org=os.environ.get("BRAINTRUST_ORG_NAME"),
        )
        return replace(opts, **overrides) if overrides else opts


def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()  # walks up from cwd; no-op if no .env
