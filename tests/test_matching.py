"""
Tests for the matching engine.

The one that matters most is `test_no_double_booking_under_concurrency`: it fires
many threads at the same small driver pool at once and asserts that every driver
is claimed at most once. That's the property the atomic lock exists to guarantee,
and it's the bug (a check-then-set race) that this design is built to prevent.
"""

from __future__ import annotations

import threading

from ride_router.locks import InMemoryLock
from ride_router.matching import Driver, match_driver
from ride_router.providers import StaticProvider, fetch_candidates


def _roster(n: int) -> list[Driver]:
    return [
        Driver(driver_id=f"d-{i}", name=f"Driver {i}", rating=4.5, distance_km=float(i))
        for i in range(n)
    ]


def test_picks_closest_then_highest_rated():
    drivers = [
        Driver("far", "Far", rating=5.0, distance_km=10.0),
        Driver("near", "Near", rating=4.0, distance_km=1.0),
    ]
    result = match_driver(drivers, InMemoryLock())
    assert result.matched
    assert result.driver.driver_id == "near"


def test_no_candidates_is_a_clean_miss():
    result = match_driver([], InMemoryLock())
    assert not result.matched
    assert result.reason == "no_candidates"


def test_provider_failure_fails_closed():
    class Boom:
        def nearby_drivers(self, lat, lng):
            raise RuntimeError("provider down")

    assert fetch_candidates(Boom(), 0.0, 0.0) == []


def test_provider_garbage_fails_closed():
    class Garbage:
        def nearby_drivers(self, lat, lng):
            return "not a list"

    assert fetch_candidates(Garbage(), 0.0, 0.0) == []


def test_static_provider_roundtrips():
    roster = _roster(3)
    assert fetch_candidates(StaticProvider(roster), 0.0, 0.0) == roster


def test_no_double_booking_under_concurrency():
    """Many riders, few drivers, all at once: no driver may be claimed twice."""
    lock = InMemoryLock()
    drivers = _roster(5)
    matched_ids: list[str] = []
    guard = threading.Lock()

    def rider():
        result = match_driver(drivers, lock)
        if result.matched:
            with guard:
                matched_ids.append(result.driver.driver_id)

    threads = [threading.Thread(target=rider) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # At most one match per driver, and no duplicates.
    assert len(matched_ids) == len(set(matched_ids))
    assert len(matched_ids) <= len(drivers)
