# The project lives within the free search-API tier

The search API is used on its free tier: 250 searches per month, with no intention of upgrading. That
ceiling is low enough to be an architectural input rather than an operational detail, so the design
absorbs it in four ways: the remaining balance is checked before every billed call (that check is
itself free), a reserve is held back that scheduled work may not touch, repeat searches inside a
short window are served from cache, and the number of standing Watches is capped.

Daily price checks dominate the budget — one call per Watch per day, so five Watches consume 150 of
the 250 before anything else happens.

## Considered Options

Checking Watches every other day would halve their cost. It was rejected because a Watch exists to
catch the moment a price crosses its target, and a sale lasting a single day is exactly the moment
worth catching; halving the sampling rate mostly discards the value the feature is for.

## Consequences

Balance is read from the API rather than counted locally, because a local counter drifts and the
authoritative number is free to fetch. Adding a sixth Watch has to be a deliberate act with a warning
attached, not a silent overspend. And "find the cheapest merchant" stays an explicit, per-product
request: applying it to a whole result page would spend a sixth of the monthly budget on one search.
