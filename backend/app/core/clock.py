"""The one place "now" comes from. Rate-limit windows and the timestamps
written to rate_limit_events both read it, so tests can move the clock
(monkeypatch `app.core.clock.now`) without the two disagreeing. Always call
`clock.now()` through the module, never `from ... import now`."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
