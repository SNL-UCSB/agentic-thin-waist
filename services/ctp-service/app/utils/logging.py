"""
logging.py — Structured logging setup for the CTP Service.

Call :func:`configure_logging` once at application startup.  After that,
every ``logging.getLogger(name)`` call returns a logger that emits JSON lines
to *stdout* (suitable for log aggregation systems) or human-readable text
(suitable for local development).

Usage
~~~~~
.. code-block:: python

    from app.utils.logging import configure_logging
    configure_logging(level="INFO", json_format=False)
    logger = logging.getLogger(__name__)
    logger.info("Pipeline started", extra={"pcap": "/data/trace.pcap"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class _JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Each record includes:
    - ``timestamp`` — ISO-8601 UTC
    - ``level``
    - ``logger``
    - ``message``
    - ``module``, ``function``, ``line``
    - Any *extra* fields passed to the log call
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Merge any extra fields injected by the caller
        skip_keys = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())
        skip_keys.update({"message", "asctime", "msg", "args"})
        for key, value in record.__dict__.items():
            if key not in skip_keys:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
) -> None:
    """Configure the root logger for the CTP Service.

    Should be called once at application startup (e.g. in ``main.py``).
    Subsequent calls are idempotent — existing handlers are replaced to avoid
    duplicate output.

    Args:
        level: Python logging level string (``DEBUG``, ``INFO``, ``WARNING``,
            ``ERROR``, ``CRITICAL``).  Case-insensitive.
        json_format: When ``True``, emit JSON lines suitable for log
            aggregation.  When ``False``, emit human-readable text.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if json_format:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Remove any handlers added by earlier basicConfig calls
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("scapy.runtime", "scapy.loading", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
