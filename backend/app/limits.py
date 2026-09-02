from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self.hits.clear()

    def hit(self, key: str, limit: int, window: float) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        q = self.hits[key]
        cutoff = now - window
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        q.append(now)


limiter = SlidingWindowLimiter()
