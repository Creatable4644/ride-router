# ride-router

A small, well-structured **driver-matching service**: given a ride request, it picks the best eligible, available driver and *atomically* claims them so two concurrent requests can never grab the same driver.

It's intentionally compact. The goal isn't feature coverage — it's to show how I structure a real-time routing system: clean separation between the matching policy and the plumbing, a concurrency guarantee that actually holds under load, and honest failure handling.

## Why this exists

I maintain a production lead-routing API that does this kind of work at ~2,000 requests/second. This project distills the parts of that problem that are interesting and portable — real-time matching, safe concurrent claiming, fail-closed external calls — into something small enough to read in a few minutes.

## The design in one screen

```
ride_router/
  matching.py    # the core policy: rank candidates, claim the best one atomically
  locks.py       # the claim-lock: Redis SET-NX in prod, in-memory for the demo
  providers.py   # the external driver supply, wrapped to fail closed
  app.py         # a thin Flask layer + a runnable demo
tests/
  test_matching.py
```

Three ideas do most of the work:

**1. The matching policy is pure and isolated.** `matching.py` doesn't know about HTTP, databases, or Redis — those are injected. That's what lets the ranking and claiming logic be read and unit-tested on its own, without spinning up any infrastructure.

**2. Claiming a driver is a single atomic operation.** The obvious approach — "check if the driver is free, then mark them taken" — has a race: two requests can both see "free" before either writes "taken," and both claim the same driver. Instead, the claim is one atomic step (`SET key value NX EX ttl` in Redis; a single guarded critical section in the in-memory version). If the claim fails, the driver was taken by a concurrent request, so we move on to the next-best candidate rather than retrying the same one. `tests/test_matching.py::test_no_double_booking_under_concurrency` fires 50 concurrent riders at 5 drivers and asserts no driver is ever claimed twice.

**3. External calls fail closed, and visibly.** The driver-supply call can error or return garbage with a 200. `providers.py` turns any such failure into a safe empty candidate list (never "assume everyone's available," which would over-route to busy drivers) and logs it at WARNING so a spike in empty results is visible instead of silently masquerading as "no drivers nearby."

## Run it

```bash
pip install -r requirements.txt

# Run the tests (the concurrency test is the interesting one)
pytest -q

# Or run the demo API
python -m ride_router.app
# then:
curl -s localhost:5000/match -X POST -H 'content-type: application/json' \
  -d '{"lat": 40.5, "lng": -111.9}'
```

## What I'd add next (and deliberately left out)

Kept out to stay readable: a real HTTP availability client, persistence, retry/backoff on the claim TTL, metrics, and auth. The point here is the shape of the core, not the surface area — those are straightforward extensions of the structure above.
