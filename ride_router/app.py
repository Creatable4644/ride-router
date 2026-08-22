"""
A thin HTTP layer over the matching engine.

The endpoint does as little as possible: parse the request, call the engine, and
shape the response. All the real logic lives in `matching.py` and is testable
without ever starting a web server. Keeping the transport layer thin is what
lets the interesting part stay readable and small for demonstration purposes.

Run the demo:  python -m ride_router.app
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request

from .locks import InMemoryLock
from .matching import Driver, match_driver
from .providers import StaticProvider, fetch_candidates

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(provider, lock) -> Flask:
    app = Flask(__name__)

    @app.get("/healthcheck")
    def healthcheck():
        return "healthy", 200

    @app.post("/match")
    def match():
        body = request.get_json(silent=True) or {}
        lat = body.get("lat")
        lng = body.get("lng")
        if lat is None or lng is None:
            return jsonify({"matched": False, "reason": "missing_location"}), 400

        candidates = fetch_candidates(provider, lat, lng)
        result = match_driver(candidates, lock)

        # Note: we return 200 even when unmatched. To the rider's client, "no
        # driver available" is a normal outcome, not an error — the same
        # response shape covers both, and the `reason` field carries the detail.
        return jsonify(
            {
                "matched": result.matched,
                "reason": result.reason,
                "driver": (
                    {
                        "driver_id": result.driver.driver_id,
                        "name": result.driver.name,
                        "rating": result.driver.rating,
                        "distance_km": result.driver.distance_km,
                    }
                    if result.driver
                    else None
                ),
            }
        ), 200

    return app


def _demo_app() -> Flask:
    roster = [
        Driver(driver_id="d-101", name="Ana", rating=4.9, distance_km=2.1),
        Driver(driver_id="d-102", name="Bo", rating=4.6, distance_km=1.4),
        Driver(driver_id="d-103", name="Cy", rating=4.8, distance_km=3.8),
    ]
    return create_app(StaticProvider(roster), InMemoryLock())


if __name__ == "__main__":
    _demo_app().run(port=5000)
