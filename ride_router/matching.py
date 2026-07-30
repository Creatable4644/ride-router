"""
Driver matching: given a ride request, pick the best eligible, available driver
and atomically claim them so no two concurrent requests can grab the same driver.

This module is deliberately small and pure. It does not know about HTTP, the
database, or any external provider — those are injected as dependencies (see
`providers.py`). That separation is the whole point: the matching
policy can be read, reasoned about, and unit-tested on its own.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Driver:
    driver_id: str
    name: str
    rating: float
    # Distance from the rider, in km, at request time.
    distance_km: float


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    driver: Driver | None = None
    # A short, machine-readable reason, useful for logs and for answering
    # "why didn't I get a driver?" without re-deriving it from raw logs later.
    reason: str = ""


class Lock(Protocol):
    """A claim-lock over a driver. The implementation must make claiming atomic.

    `claim` MUST return True only for the caller that actually acquired the
    claim, and False for everyone else — even under concurrent calls for the
    same driver_id. This is the contract that prevents double-booking.
    """

    def claim(self, driver_id: str, ttl_seconds: int) -> bool: ...

    def release(self, driver_id: str) -> None: ...


def _score(driver: Driver) -> float:
    """Rank drivers: closer is better, higher-rated is better.

    Kept as a single named function so the ranking policy lives in exactly one
    place and can be changed (or A/B'd) without touching the matching flow.
    """
    # Distance dominates; rating breaks ties and nudges within a band.
    return driver.distance_km - (driver.rating * 0.5)


def match_driver(
    candidates: list[Driver],
    lock: Lock,
    *,
    claim_ttl_seconds: int = 30,
    max_attempts: int = 5,
) -> MatchResult:
    """Pick and atomically claim the best available driver from `candidates`.

    We rank all candidates once, then walk them best-first, attempting an atomic
    claim on each. The first successful claim wins. If a claim fails, that driver
    was taken by a concurrent request between ranking and claiming — so we move on
    to the next-best rather than retrying the same one (which is the mistake that
    causes retry storms and hides the real contention).
    """
    if not candidates:
        return MatchResult(matched=False, reason="no_candidates")

    ranked = sorted(candidates, key=_score)

    for driver in ranked[:max_attempts]:
        if lock.claim(driver.driver_id, ttl_seconds=claim_ttl_seconds):
            logger.info("matched rider to driver %s", driver.driver_id)
            return MatchResult(matched=True, driver=driver, reason="matched")
        logger.info(
            "driver %s was claimed by a concurrent request; trying next",
            driver.driver_id,
        )

    # Everyone we tried was claimed out from under us. That's a real, visible
    # outcome (high contention / low supply) — not an error to swallow.
    return MatchResult(matched=False, reason="all_candidates_claimed")
