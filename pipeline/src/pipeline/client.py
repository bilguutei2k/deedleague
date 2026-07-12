"""Polite GraphQL transport + raw-snapshot provenance.

Politeness: ~1.5 req/s (min-interval throttle), retry-with-backoff on 5xx/timeout.
Concurrency is bounded by the caller; the backfill is sequential, so a simple
process-wide min-interval throttle is sufficient and keeps provenance ordering clean.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from .config import GRAPHQL_URL, PolitenessConfig, snapshot_dir, snapshot_uri_prefix


class MsportsClient:
    def __init__(
        self,
        url: str | None = None,
        politeness: PolitenessConfig | None = None,
    ) -> None:
        self.url = url or GRAPHQL_URL
        self.politeness = politeness or PolitenessConfig()
        self.headers = {
            "user-agent": "deedleague-index/0.1 (analytics ingest; contact: project owner)",
            "referer": "https://www.msports.mn/",
            "content-type": "application/json",
            "authorization": "",  # source returns full data with empty auth
        }
        self._min_interval = 1.0 / max(self.politeness.requests_per_second, 0.01)
        self._last_request_at = 0.0
        self._client = httpx.Client(timeout=60.0, headers=self.headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MsportsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def post_graphql(
        self,
        operation_name: str,
        variables: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        """POST a GraphQL operation, retrying on 5xx/timeout. Raises on GraphQL errors."""
        body = {"operationName": operation_name, "variables": variables, "query": query}
        last_exc: Exception | None = None
        for attempt in range(self.politeness.max_retries):
            self._throttle()
            try:
                self._last_request_at = time.monotonic()
                resp = self._client.post(self.url, json=body)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"server {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("errors"):
                    raise RuntimeError(
                        f"GraphQL errors for {operation_name}: "
                        f"{json.dumps(payload['errors'])[:400]}"
                    )
                return payload
            except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                last_exc = exc
                sleep = self.politeness.backoff_seconds * (2**attempt)
                time.sleep(sleep)
        raise RuntimeError(
            f"{operation_name} failed after {self.politeness.max_retries} attempts: {last_exc}"
        )

    def fetch_and_snapshot(
        self,
        operation_name: str,
        variables: dict[str, Any],
        query: str,
        snapshot_label: str,
    ) -> tuple[dict[str, Any], str]:
        """Fetch locally and return its local path or configured durable reference."""
        payload = self.post_graphql(operation_name, variables, query)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        unique_suffix = time.time_ns()
        out_dir = os.path.abspath(snapshot_dir())
        os.makedirs(out_dir, exist_ok=True)
        filename = f"{snapshot_label}_{ts}_{unique_suffix}.json"
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        prefix = snapshot_uri_prefix()
        return payload, f"{prefix}/{filename}" if prefix else path
