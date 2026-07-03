"""Async token bucket rate limiter."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async token bucket rate limiter.

    Enforces a maximum number of requests within a time window.
    Thread-safe for asyncio use.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.tokens: list[float] = []  # Timestamps of token acquisitions
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire a token. Returns True if allowed, False if rate limited."""
        async with self._lock:
            now = time.monotonic()
            # Expire tokens outside the window
            cutoff = now - self.window_seconds
            self.tokens = [t for t in self.tokens if t > cutoff]

            if len(self.tokens) < self.max_requests:
                self.tokens.append(now)
                return True

            return False

    async def wait_and_acquire(self) -> None:
        """Block until a token is available, then acquire it."""
        while not await self.acquire():
            # Calculate how long until the oldest token expires
            async with self._lock:
                if self.tokens:
                    oldest = self.tokens[0]
                    wait_time = oldest + self.window_seconds - time.monotonic()
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
            await asyncio.sleep(0.5)  # Small sleep to avoid busy-waiting


class GlobalRateLimiter:
    """A registry of per-domain rate limiters."""

    def __init__(self, default_max: int = 10, default_window: int = 60):
        self._limiters: dict[str, RateLimiter] = {}
        self._default_max = default_max
        self._default_window = default_window
        self._lock = asyncio.Lock()

    async def get_limiter(self, domain: str, max_requests: int | None = None,
                          window_seconds: int | None = None) -> RateLimiter:
        """Get or create a rate limiter for a domain."""
        async with self._lock:
            if domain not in self._limiters:
                self._limiters[domain] = RateLimiter(
                    max_requests=max_requests or self._default_max,
                    window_seconds=window_seconds or self._default_window,
                )
            return self._limiters[domain]
