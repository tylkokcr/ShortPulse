"""Request throttling.

Credits bound what a render *costs*, not how fast a client can ask for
things. Without a limit, one account can flood the render queue ahead of
everyone else's work, and an unauthenticated caller can hammer the cheap
endpoints for free.

A token bucket, because the useful shape here is "a burst is fine, a
sustained flood is not": submitting three renders back to back is normal
behaviour, three hundred is not.

State is per-process. With several instances the effective limit is
multiplied by the instance count — which still bounds abuse, just less
tightly. Moving it to Postgres or Redis would fix that at the cost of a
round trip on every request; worth doing when there is more than one
instance, not before.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Bucket:
    tokens: float
    last_refill: float


@dataclass
class TokenBucketLimiter:
    """`capacity` requests up front, refilled at `capacity / per_seconds`.

    Callers that never come back are forgotten on the next sweep, so a
    stream of one-off IPs can't grow this without bound.
    """

    capacity: int
    per_seconds: float
    _buckets: dict[str, Bucket] = field(default_factory=dict)
    # Called through the module rather than bound at class-definition time,
    # so the clock is read when an instance is created — which is also what
    # makes the refill behaviour testable with a fake clock.
    _last_sweep: float = field(default_factory=lambda: time.monotonic())

    def _sweep(self, now: float) -> None:
        # A bucket that has had time to refill completely carries no
        # information, so dropping it changes nothing except memory.
        if now - self._last_sweep < self.per_seconds:
            return
        self._buckets = {
            key: b
            for key, b in self._buckets.items()
            if now - b.last_refill < self.per_seconds
        }
        self._last_sweep = now

    def check(self, key: str) -> float | None:
        """Take a token. Returns None if allowed, else seconds to wait."""
        now = time.monotonic()
        self._sweep(now)

        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = Bucket(tokens=self.capacity - 1, last_refill=now)
            return None

        rate = self.capacity / self.per_seconds
        bucket.tokens = min(self.capacity, bucket.tokens + (now - bucket.last_refill) * rate)
        bucket.last_refill = now

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return None
        return (1 - bucket.tokens) / rate
