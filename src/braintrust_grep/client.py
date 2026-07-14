"""BtqlClient: a rate-limit-aware, retrying BTQL HTTP client.

Bakes in every correctness gotcha we hit in production:

- **Pacing** to stay under the org limit (~20 requests / 60s).
- **Retry** on 408/429/500/502/503/504 with capped exponential backoff + jitter,
  honoring ``Retry-After``. (408/504 are the *primary* timeout failures.)
- **Redirect + gzip**: large results 303-redirect to a gzipped S3 object.
- **Cursor pagination** using ``limit`` + ``cursor: '<token>'``.
- Typed errors instead of ``sys.exit``.
"""

from __future__ import annotations

import gzip
import json
import random
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import httpx

from .clock import Clock, RealClock
from .config import ClientOptions
from .errors import BtqlHttpError, QueryTimeoutError, RateLimitError

if TYPE_CHECKING:
    from .query import BtqlQuery

_TIMEOUT_HINT = (
    "query exceeded Braintrust's 30s limit; narrow the `created` window, prefer "
    "MATCH + cursor pagination, and avoid IN (...)/LIKE over wide windows."
)


class BtqlClient:
    def __init__(
        self,
        options: ClientOptions,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
    ):
        self.options = options
        self._clock = clock or RealClock()
        self._rng = rng or random.Random()
        self._last_request: float | None = None
        self._client = httpx.Client(
            timeout=options.request_timeout,
            follow_redirects=options.follow_redirects,
            transport=transport,
            headers={
                "Authorization": f"Bearer {options.api_key}",
                "Content-Type": "application/json",
            },
        )

    def __enter__(self) -> BtqlClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- public API -------------------------------------------------------
    def query(self, btql: str) -> dict[str, Any]:
        """Run one BTQL query string, returning the decoded JSON envelope."""
        opts = self.options
        last_status = 0
        last_body = ""
        for attempt in range(opts.max_retries):
            self._pace()
            resp = self._client.post(opts.base_url, json={"query": btql})
            if resp.status_code == 200:
                return self._decode(resp)
            last_status, last_body = resp.status_code, _truncate(resp.text)
            if resp.status_code in opts.retry_statuses and attempt < opts.max_retries - 1:
                self._clock.sleep(self._backoff(attempt, resp))
                continue
            raise self._error(resp.status_code, last_body)
        raise self._error(last_status, last_body)

    def paginate(
        self, query: BtqlQuery, *, max_rows: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield rows across pages, following the ``cursor`` token."""
        cursor: str | None = None
        yielded = 0
        while True:
            body = self.query(query.render(limit=self.options.page_size, cursor=cursor))
            rows = body.get("data", [])
            if not rows:
                return
            for row in rows:
                yield row
                yielded += 1
                if max_rows is not None and yielded >= max_rows:
                    return
            cursor = body.get("cursor")
            if not cursor:
                return

    # -- internals --------------------------------------------------------
    def _pace(self) -> None:
        interval = self.options.min_request_interval
        if self._last_request is not None:
            gap = self._clock.now() - self._last_request
            if gap < interval:
                self._clock.sleep(interval - gap)
        self._last_request = self._clock.now()

    def _backoff(self, attempt: int, resp: httpx.Response) -> float:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after
        base = min(self.options.backoff_cap, self.options.backoff_base ** (attempt + 1))
        return base + self._rng.random() * base * 0.25  # up to +25% jitter

    def _error(self, status: int, body: str) -> BtqlHttpError:
        if status == 429:
            return RateLimitError(status, body, hint="reduce request rate (org limit ~20/60s).")
        if status in (408, 504):
            return QueryTimeoutError(status, body, hint=_TIMEOUT_HINT)
        return BtqlHttpError(status, body)

    @staticmethod
    def _decode(resp: httpx.Response) -> dict[str, Any]:
        content = resp.content
        if content[:2] == b"\x1f\x8b":  # gzip magic (redirected S3 payloads)
            content = gzip.decompress(content)
        return json.loads(content)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)  # delta-seconds form; HTTP-date form is ignored
    except ValueError:
        return None


def _truncate(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
