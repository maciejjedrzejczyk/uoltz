"""Thin client for the signal-cli-rest-api with retry logic."""

import time
import httpx
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds between retries


class SignalClient:
    def __init__(self, base_url: str, number: str):
        self.base_url = base_url.rstrip("/")
        self.number = number
        self._http = httpx.Client(base_url=self.base_url, timeout=60)

    def _retry(self, operation: str, func, *args, **kwargs):
        """Execute a function with retries on failure."""
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "Signal %s failed (attempt %d/%d): %s — retrying in %ds",
                        operation, attempt + 1, MAX_RETRIES, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Signal %s failed after %d attempts: %s",
                        operation, MAX_RETRIES, exc,
                    )
        return last_exc

    # ── Receive ──────────────────────────────────────────────
    def receive(self) -> list[dict]:
        """Poll for new incoming messages with retry."""
        def _do():
            resp = self._http.get(f"/v1/receive/{self.number}")
            resp.raise_for_status()
            return resp.json()

        result = self._retry("receive", _do)
        if isinstance(result, Exception):
            return []
        return result

    # ── Send ─────────────────────────────────────────────────
    def send(self, recipient: str, message: str) -> bool:
        """Send a text message to a single recipient with retry.

        Long messages are chunked at 2000 chars. Each chunk is retried
        independently on failure.
        """
        chunks = [message[i : i + 2000] for i in range(0, len(message), 2000)]
        for i, chunk in enumerate(chunks):
            def _do(text=chunk):
                resp = self._http.post(
                    "/v2/send",
                    json={
                        "message": text,
                        "number": self.number,
                        "recipients": [recipient],
                    },
                )
                resp.raise_for_status()
                return True

            result = self._retry(f"send (chunk {i+1}/{len(chunks)})", _do)
            if isinstance(result, Exception):
                return False
        return True

    # ── Health ───────────────────────────────────────────────
    def is_healthy(self) -> bool:
        try:
            resp = self._http.get("/v1/about")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
