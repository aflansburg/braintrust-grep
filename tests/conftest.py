"""Shared test helpers: an httpx MockTransport that replays queued responses."""

from __future__ import annotations

import gzip
import json
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from braintrust_grep.client import BtqlClient
from braintrust_grep.clock import FakeClock
from braintrust_grep.config import ClientOptions


def json_response(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def gzip_response(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    body = gzip.compress(json.dumps(payload).encode())
    return httpx.Response(status, content=body)


def redirect_response(location: str = "https://s3.example/obj") -> httpx.Response:
    return httpx.Response(303, headers={"Location": location})


def error_response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, text=f"error {status}", headers=headers or {})


@dataclass
class Recorder:
    """Replays queued responses in order and records each request's parsed body."""

    responses: list[httpx.Response]
    requests: list[httpx.Request] = field(default_factory=list)
    bodies: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.content:
            try:
                self.bodies.append(json.loads(request.content))
            except ValueError:
                self.bodies.append({})
        if not self.responses:
            raise AssertionError("no more queued responses")
        return self.responses.pop(0)


def make_client(
    responses: list[httpx.Response], **option_overrides: Any
) -> tuple[BtqlClient, FakeClock, Recorder]:
    recorder = Recorder(list(responses))
    clock = FakeClock()
    opts = ClientOptions(api_key="test-key", **option_overrides)
    client = BtqlClient(
        opts,
        transport=httpx.MockTransport(recorder),
        clock=clock,
        rng=random.Random(0),
    )
    return client, clock, recorder
