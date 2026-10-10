"""Token accounting for one request, and a rough cost estimate.

The capture route starts a `UsageAccumulator` in a ContextVar before calling
the analyzer; the analyzers add the provider-reported tokens from every call
they make (the main analysis and each graph-localization pass). The
localization calls run under `asyncio.gather`, which copies the context into
each task, so they all see the same accumulator object. Nothing is stored on
the analyzer itself, because it is a process-wide singleton shared by
concurrent requests.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class UsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0


_current: ContextVar[UsageAccumulator | None] = ContextVar("usage_accumulator", default=None)


def start_accumulator() -> UsageAccumulator:
    accumulator = UsageAccumulator()
    _current.set(accumulator)
    return accumulator


def record_usage(input_tokens: int | None, output_tokens: int | None) -> None:
    """Called by provider code after each API call. A no-op outside a
    request that started an accumulator (tests, scripts)."""
    accumulator = _current.get()
    if accumulator is None:
        return
    accumulator.input_tokens += input_tokens or 0
    accumulator.output_tokens += output_tokens or 0


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    prices = get_settings().model_prices_usd_per_mtok.get(model or "")
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def record_response_usage(response: object, input_attr: str, output_attr: str) -> None:
    """Reads token counts off a provider response. `usage` is always present
    on real SDK responses; the lookup is tolerant so a response object
    without it (a test double, a future SDK change) costs nothing instead of
    failing a capture over bookkeeping."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    record_usage(getattr(usage, input_attr, None), getattr(usage, output_attr, None))
