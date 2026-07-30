"""
The external supply of drivers.

In a real system this is a network call to one or more driver-availability
services. Those calls fail, time out, and occasionally return nonsense with a
200 status. The job of this layer is to turn all of that into one honest,
predictable answer: a (possibly empty) list of `Driver`s, and never a surprise.

Design choices worth noting:

- **Fail closed.** If the provider errors or returns something unexpected, we
  return an empty candidate list, not "assume everyone is available." Over-
  routing to drivers who may already be busy is worse than saying "no driver
  right now," so the safe default is the empty list.

- **The caller can always tell what happened.** We log the failure at WARNING
  (something worth looking at) rather than swallowing it silently, so a spike in
  empty results is visible instead of masquerading as "no drivers nearby."
"""

from __future__ import annotations

import logging
from typing import Protocol

from .matching import Driver

logger = logging.getLogger(__name__)


class AvailabilityProvider(Protocol):
    def nearby_drivers(self, lat: float, lng: float) -> list[Driver]: ...


class StaticProvider:
    """A fixed roster, for the demo and tests. Swap for a real HTTP client."""

    def __init__(self, drivers: list[Driver]):
        self._drivers = drivers

    def nearby_drivers(self, lat: float, lng: float) -> list[Driver]:
        return list(self._drivers)


def fetch_candidates(provider: AvailabilityProvider, lat: float, lng: float) -> list[Driver]:
    """Get nearby drivers, converting any failure into a safe empty list.

    This wrapper exists so every call site gets the same fail-closed behavior
    for free, instead of each one re-implementing (and subtly varying) its own
    error handling.
    """
    try:
        drivers = provider.nearby_drivers(lat, lng)
    except Exception:  # noqa: BLE001 - deliberately broad: any failure → fail closed
        logger.warning("availability provider failed; returning no candidates", exc_info=True)
        return []

    if not isinstance(drivers, list):
        logger.warning("availability provider returned a non-list; treating as empty")
        return []

    return drivers
