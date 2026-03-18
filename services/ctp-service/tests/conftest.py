"""
conftest.py — pytest configuration for the CTP Service test suite.

Heavy optional dependencies (numpy, pandas, scapy, psycopg2) are stubbed
out via sys.modules before any app code is imported.  This allows unit tests
to run in a minimal environment without requiring native libraries or a
running database.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _stub(name: str) -> MagicMock:
    """Create a named MagicMock and register it (and parent packages) in sys.modules."""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            sys.modules[parent] = MagicMock(name=parent)
    return sys.modules[name]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Stub heavy / native dependencies that are not needed for route unit tests
# ---------------------------------------------------------------------------

for _mod in [
    # Numerical / data
    "numpy",
    "numpy.core",
    "numpy._core",
    "numpy._core.multiarray",
    "pandas",
    "pandas.core",
    # PCAP processing
    "scapy",
    "scapy.all",
    "scapy.utils",
    "scapy.layers",
    "scapy.layers.all",
    "scapy.layers.inet",
    # Database driver
    "psycopg2",
    "psycopg2.pool",
    "psycopg2.extras",
    "psycopg2.extensions",
]:
    _stub(_mod)
