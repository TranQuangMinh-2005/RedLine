"""In-memory Rules-of-Engagement limits for the single-user sandbox scenario."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimitExceeded(RuntimeError):
    pass


class TokenBudgetExceeded(RuntimeError):
    pass


class RoeBudget:
    """Process-local limiter; sufficient for the one-process sandbox target."""

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._tokens: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def begin_request(
        self,
        key: str,
        *,
        max_requests_per_minute: int,
        max_tokens_total: int,
    ) -> None:
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and now - timestamps[0] >= 60:
                timestamps.popleft()
            if len(timestamps) >= max_requests_per_minute:
                raise RateLimitExceeded("request rate limit reached")
            if self._tokens[key] >= max_tokens_total:
                raise TokenBudgetExceeded("token budget reached")
            timestamps.append(now)

    def record_tokens(self, key: str, tokens: int) -> None:
        with self._lock:
            self._tokens[key] += max(0, int(tokens))

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._tokens.clear()


roe_budget = RoeBudget()
