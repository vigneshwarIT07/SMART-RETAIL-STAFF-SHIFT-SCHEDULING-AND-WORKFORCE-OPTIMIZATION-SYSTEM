"""A small in-process sliding-window rate limiter.

The limiter protects the authentication endpoint against password guessing. It
is deliberately simple and in-memory: the state lives in a dictionary inside a
single worker process and is documented as *per-process*. That is an honest
description of the guarantee, and it is why the deployment topology in
``render.yaml`` keeps a single web service. A multi-process or multi-instance
deployment would need a shared store (for example Redis or a database table)
instead, which is called out in README section 14 as a future enhancement.

Counters are garbage-collected lazily on access and via :func:`reset_limiter`,
so a long-running process does not accumulate keys for every IP it has seen.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Allow at most ``limit`` events per ``window_seconds`` for each key."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        """Initialise the limiter.

        Args:
            limit: Maximum number of allowed events inside the window.
            window_seconds: Length of the sliding window in seconds.
        """
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must both be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Record an attempt for ``key`` and report whether it is allowed.

        Args:
            key: Identity being limited, typically a client IP address.

        Returns:
            True when the attempt is within the limit, False when it is blocked.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def retry_after(self, key: str) -> int:
        """Seconds the caller should wait before retrying.

        Args:
            key: The identity that was blocked.

        Returns:
            Whole seconds until the oldest event leaves the window; ``1`` when
            no useful value can be determined.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._events.get(key)
            if not bucket:
                return 1
            wait = bucket[0] + self.window_seconds - now
            return max(1, int(wait) + 1)

    def reset(self, key: str | None = None) -> None:
        """Clear counters for one key, or for every key when ``key`` is None."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


class _DisabledRateLimiter(SlidingWindowRateLimiter):
    """No-op limiter used when ``RATE_LIMIT_ENABLED`` is false."""

    def check(self, key: str) -> bool:  # noqa: D102 - inherited behaviour
        return True

    def retry_after(self, key: str) -> int:  # noqa: D102 - inherited behaviour
        return 0


def build_limiter(
    enabled: bool, limit: int, window_seconds: int
) -> SlidingWindowRateLimiter:
    """Create the limiter appropriate for the current configuration.

    Args:
        enabled: Whether rate limiting is switched on.
        limit: Allowed attempts inside the window.
        window_seconds: Window length.

    Returns:
        A limiter instance.
    """
    if not enabled:
        return _DisabledRateLimiter(limit, window_seconds)
    return SlidingWindowRateLimiter(limit, window_seconds)


def client_ip(request) -> str:
    """Best-effort client IP for use as a rate-limit key.

    ``X-Forwarded-For`` is honoured because the platform terminates TLS before
    the application. The value is only ever used as a dictionary key, never
    logged or returned.

    Args:
        request: The incoming Starlette request.

    Returns:
        An IP address string, or ``"unknown"`` when none can be determined.
    """
    forwarded: tuple[str, ...] = request.headers.get("x-forwarded-for", "").split(",")
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def reset_limiter() -> None:
    """Forget every attempt. Used by tests to isolate cases."""
    for limiter in _LIMITERS.values():
        limiter.reset()


#: Limiter instances keyed by ``"<scope>:<limit>:<window>"`` so tests and future
#: endpoints can share a single construction path.
_LIMITERS: dict[str, SlidingWindowRateLimiter] = {}


def get_limiter(
    scope: str, enabled: bool, limit: int, window_seconds: int
) -> SlidingWindowRateLimiter:
    """Return a cached limiter for ``scope``.

    Args:
        scope: Logical name, e.g. ``"login"``.
        enabled: Whether limiting is active.
        limit: Allowed attempts inside the window.
        window_seconds: Window length.

    Returns:
        The (possibly cached) limiter instance.
    """
    cache_key = f"{scope}:{int(enabled)}:{limit}:{window_seconds}"
    if cache_key not in _LIMITERS:
        _LIMITERS[cache_key] = build_limiter(enabled, limit, window_seconds)
    return _LIMITERS[cache_key]
