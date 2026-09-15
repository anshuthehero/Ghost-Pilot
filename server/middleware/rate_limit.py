"""
Rate Limiting Middleware for Ghost Copilot.
Sliding-Window Log Rate Limiting per authenticated user ID / client IP.
"""

import time
import threading
from collections import defaultdict
from fastapi import Request, HTTPException, status
from server.config.settings import settings

_MAX_TRACKED_IDENTIFIERS = 50_000  # memory cap — evict oldest if exceeded


class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self.lock = threading.Lock()
        self.history: dict = {}

    def is_rate_limited(self, identifier: str) -> bool:
        now = time.time()
        window_start = now - 60.0

        with self.lock:
            # Evict oldest entries when the dict grows too large (M-3 memory fix)
            if len(self.history) >= _MAX_TRACKED_IDENTIFIERS:
                oldest = sorted(self.history, key=lambda k: max(self.history[k], default=0))
                for k in oldest[: len(self.history) // 4]:
                    del self.history[k]

            valid_timestamps = [t for t in self.history.get(identifier, []) if t > window_start]
            if len(valid_timestamps) >= self.rpm:
                return True
            valid_timestamps.append(now)
            self.history[identifier] = valid_timestamps
            return False


solve_limiter = RateLimiter(requests_per_minute=settings.RATE_LIMIT_SOLVE_RPM)
transcribe_limiter = RateLimiter(requests_per_minute=settings.RATE_LIMIT_TRANSCRIBE_RPM)


async def check_rate_limit(request: Request, limiter: RateLimiter):
    """FastAPI dependency to rate limit sensitive endpoints.
    Keys on authenticated user_id extracted from request.state (set by auth dependency),
    falling back to client IP. This prevents bypass via multiple tokens (M-3 fix)."""
    # Use user id if the auth dependency already resolved it onto request.state
    user_id = getattr(getattr(request, "state", None), "user_id", None)
    ip = request.client.host if request.client else "127.0.0.1"
    identifier = user_id if user_id else ip

    if limiter.is_rate_limited(identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down your requests."
        )
