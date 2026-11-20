"""The sweep test suite.

P4-S1C added three short, time-based controls: the worker status/rows cache
(worker_link.STATUS_TTL), the screens' plan cache (app.PLAN_CACHE_SECONDS)
and poll pacing (public.POLL_INTERVALS). A browser cannot change the worker's
answer between two requests a millisecond apart, or poll every millisecond —
but most tests here do both on purpose. So the suite starts with all three at
their fastest, and the tests that pin them (test_public_hardening) put the
production values, kept in PRODUCTION, back for themselves.
"""

from sweep import app as _app
from sweep import public as _public
from sweep import worker_link as _worker_link

PRODUCTION = {"status_ttl": _worker_link.STATUS_TTL,
              "plan_cache_seconds": _app.PLAN_CACHE_SECONDS,
              "poll_intervals": dict(_public.POLL_INTERVALS)}

_worker_link.STATUS_TTL = 0
_app.PLAN_CACHE_SECONDS = 0
for _route in _public.POLL_INTERVALS:
    _public.POLL_INTERVALS[_route] = 1e-9
