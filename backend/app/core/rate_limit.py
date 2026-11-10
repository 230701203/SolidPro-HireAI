"""Simple in-memory sliding-window rate limiter.

Good enough for a single process. When running several workers, back this with Redis
(same interface) so limits are shared.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False, int(window_seconds - (now - q[0])) + 1
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = InMemoryRateLimiter()


def rate_limit(scope: str, limit: int, window_seconds: int):
    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        ip = request.client.host if request.client else "unknown"
        ok, retry_after = limiter.check(f"{scope}:{ip}", limit, window_seconds)
        if not ok:
            raise AppError(
                429,
                "rate_limited",
                "Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
