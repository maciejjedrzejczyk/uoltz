"""Mutable runtime state that can be toggled via slash commands.

This is separate from config.py (which is read-only from .env).
Runtime state changes live only for the current process lifetime.
"""

import threading


class RuntimeState:
    """Thread-safe mutable runtime toggles."""

    def __init__(self):
        self._lock = threading.Lock()
        self._markdown = False
        self._debug = False
        self._max_tokens: int | None = None  # None = use config default

    @property
    def markdown(self) -> bool:
        with self._lock:
            return self._markdown

    @markdown.setter
    def markdown(self, value: bool):
        with self._lock:
            self._markdown = value

    @property
    def debug(self) -> bool:
        with self._lock:
            return self._debug

    @debug.setter
    def debug(self, value: bool):
        with self._lock:
            self._debug = value

    @property
    def max_tokens(self) -> int | None:
        with self._lock:
            return self._max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int | None):
        with self._lock:
            self._max_tokens = value


# Singleton
state = RuntimeState()
