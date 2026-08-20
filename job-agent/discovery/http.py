"""Shared HTTP helpers for discovery adapters.

Provides one resilient ``get_json`` used by every adapter so retry,
timeout, and rate-limit awareness live in a single place. Retries are
strict about only rehitting *transient* failures (timeouts, 429, 5xx);
a 400/403/404 fails fast and gets surfaced to the caller.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from config.settings import settings
from services.logging_config import get_logger

log = get_logger(__name__)

_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_DEFAULT_HEADERS = {
    "User-Agent": "JobPilot/1.0 (+discovery)",
    "Accept": "application/json,text/json,application/xml;q=0.5,*/*;q=0.1",
    "Accept-Encoding": "gzip, deflate",
}


class HTTPClientError(RuntimeError):
    """Raised when a request definitively fails after retries."""


def _sleep_seconds(attempt: int, retry_after: str | None, base: float = 0.5, cap: float = 8.0) -> float:
    """Exponential backoff with jitter, honoring a Retry-After header when present."""

    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    return delay + random.uniform(0, delay / 2)


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    retries: int = 3,
    timeout: float | None = None,
    accept_status: set[int] = frozenset({200}),
) -> Any:
    """GET ``url`` and return decoded JSON.

    - Retries on transient statuses / network errors up to ``retries`` times.
    - Respects ``Retry-After`` when the server sends one on 429/503.
    - Non-transient failures raise ``HTTPClientError`` with the last response
      status and a short body preview so callers can log context.
    """

    effective_headers = {**_DEFAULT_HEADERS, **(headers or {})}
    timeout = timeout if timeout is not None else settings.discovery_http_timeout

    async def _do(c: httpx.AsyncClient) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = await c.get(url, params=params, headers=effective_headers, timeout=timeout)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt >= retries:
                    raise HTTPClientError(f"{url} network error after {retries} attempts: {exc}") from exc
                await asyncio.sleep(_sleep_seconds(attempt, None))
                continue

            if resp.status_code in accept_status:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise HTTPClientError(
                        f"{url} returned non-JSON body (status {resp.status_code}): {resp.text[:200]}"
                    ) from exc

            if resp.status_code in _TRANSIENT_STATUSES and attempt < retries:
                await asyncio.sleep(_sleep_seconds(attempt, resp.headers.get("Retry-After")))
                last_exc = HTTPClientError(f"{url} transient {resp.status_code}")
                continue

            raise HTTPClientError(
                f"{url} failed with status {resp.status_code}: {resp.text[:200]}"
            )

        # Unreachable, but keeps mypy happy.
        raise HTTPClientError(f"{url} failed: {last_exc}")

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=timeout) as owned:
        return await _do(owned)


async def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float | None = None,
) -> str:
    """Simple text GET (no retry). Used for the rare adapter that speaks HTML."""

    effective_headers = {**_DEFAULT_HEADERS, **(headers or {})}
    timeout = timeout if timeout is not None else settings.discovery_http_timeout

    async def _do(c: httpx.AsyncClient) -> str:
        resp = await c.get(url, params=params, headers=effective_headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        raise HTTPClientError(f"{url} failed with status {resp.status_code}: {resp.text[:200]}")

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=timeout) as owned:
        return await _do(owned)
