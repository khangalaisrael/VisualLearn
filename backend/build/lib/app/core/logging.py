"""Structured logging setup.

docs/ARCHITECTURE.md §6 requires structured logs (processing time, model
used, cache hit/miss, object count, confidence) and forbids logging slide
content in production. This module only configures the log format/level;
callers are responsible for keeping slide content out of log messages.
"""

import logging
import sys

from app.core.config import get_settings

_LOG_FORMAT = (
    '{"time": "%(asctime)s", "level": "%(levelname)s", '
    '"logger": "%(name)s", "message": "%(message)s"}'
)


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format=_LOG_FORMAT, stream=sys.stdout, force=True)
