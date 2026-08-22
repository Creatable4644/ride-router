"""
Claim-locks over drivers.

Two implementations:

- `RedisLock` uses `SET key value NX EX ttl` — a single atomic operation that
  sets the key *only if it does not already exist* and gives it an expiry in the
  same call. This makes it safe in high volume concurrent requests, as there is no
  gap between checking if the driver is free, and marking them as taken - simultaneous
  requests for the same driver cannot slip through the gap. This is a conscientious choice
  over the more typical GET *then* SET solution implemented in low volume envs where it's not
  noticeable until the product scales that the 'then' part of that equation is a crack other
  requests can seep into. Ask if I learned this the hard way!

- `InMemoryLock` is a thread-safe local version so the demo and tests run with no
  external dependencies. It mirrors the same contract.
"""

from __future__ import annotations

import threading
import time


class RedisLock:
    """Atomic claim-lock backed by Redis/Valkey.

    Expects a redis-py-compatible client. Not exercised in the demo (no server),
    but this is here for representation of what I'd craft for an actual
    production env.
    """

    def __init__(self, client, key_prefix: str = "driver_claim:"):
        self._client = client
        self._prefix = key_prefix

    def claim(self, driver_id: str, ttl_seconds: int) -> bool:
        # nx=True → only set if absent; ex=ttl → auto-expire so a crashed
        # request can't hold a driver hostage forever. One round trip, atomic.
        acquired = self._client.set(
            f"{self._prefix}{driver_id}", "claimed", nx=True, ex=ttl_seconds
        )
        return bool(acquired)

    def release(self, driver_id: str) -> None:
        self._client.delete(f"{self._prefix}{driver_id}")


class InMemoryLock:
    """Thread-safe in-process claim-lock. For tests and the local demo."""

    def __init__(self):
        self._claims: dict[str, float] = {}
        self._guard = threading.Lock()

    def claim(self, driver_id: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        # The guard makes check-and-set a single critical section — the
        # in-memory equivalent of SET NX.
        with self._guard:
            expires_at = self._claims.get(driver_id)
            if expires_at is not None and expires_at > now:
                return False
            self._claims[driver_id] = now + ttl_seconds
            return True

    def release(self, driver_id: str) -> None:
        with self._guard:
            self._claims.pop(driver_id, None)
