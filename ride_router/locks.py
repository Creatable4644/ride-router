"""
Claim-locks over drivers.

Two implementations:

- `RedisLock` uses `SET key value NX EX ttl` — a single atomic operation that
  sets the key *only if it does not already exist* and gives it an expiry in the
  same call. Atomicity is what makes the claim safe under concurrency: there is
  no window between "check if free" and "mark as taken" for a second request to
  slip through. (Doing those as two steps — GET then SET — is a classic
  time-of-check/time-of-use race that lets two requests claim the same driver.)

- `InMemoryLock` is a thread-safe local version so the demo and tests run with no
  external dependencies. It mirrors the same contract.
"""

from __future__ import annotations

import threading
import time


class RedisLock:
    """Atomic claim-lock backed by Redis/Valkey.

    Expects a redis-py-compatible client. Not exercised in the demo (no server),
    but this is the shape you'd run in production.
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
