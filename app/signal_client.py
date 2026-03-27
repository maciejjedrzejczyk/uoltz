"""Thin client for the signal-cli-rest-api."""

import httpx
import logging

logger = logging.getLogger(__name__)


class SignalClient:
    def __init__(self, base_url: str, number: str):
        self.base_url = base_url.rstrip("/")
        self.number = number
        self._http = httpx.Client(base_url=self.base_url, timeout=60)

    # ── Receive ──────────────────────────────────────────────
    def receive(self) -> list[dict]:
        """Poll for new incoming messages."""
        try:
            resp = self._http.get(f"/v1/receive/{self.number}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error("Signal receive error: %s", exc)
            return []

    # ── Send ─────────────────────────────────────────────────
    def send(self, recipient: str, message: str) -> bool:
        """Send a text message to a single recipient."""
        # Chunk at 2000 chars — smaller chunks send faster and avoid timeouts
        chunks = [message[i : i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            try:
                resp = self._http.post(
                    "/v2/send",
                    json={
                        "message": chunk,
                        "number": self.number,
                        "recipients": [recipient],
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("Signal send error: %s", exc)
                return False
        return True

    # ── Health ───────────────────────────────────────────────
    def is_healthy(self) -> bool:
        try:
            resp = self._http.get("/v1/about")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
