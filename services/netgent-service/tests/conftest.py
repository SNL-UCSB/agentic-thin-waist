from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_to_local_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep client tests independent from the repo-level .env defaults."""

    monkeypatch.setenv("NETGENT_USE_LOCAL", "true")
    monkeypatch.delenv("NETGENT_NAMESPACE", raising=False)
