from __future__ import annotations

import sys
from pathlib import Path

import pytest

SHARED_DIR = Path(__file__).resolve().parents[3] / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))


@pytest.fixture(autouse=True)
def _default_to_local_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep client tests independent from the repo-level .env defaults."""

    monkeypatch.setenv("NETGENT_USE_LOCAL", "true")
    monkeypatch.delenv("NETGENT_NAMESPACE", raising=False)
