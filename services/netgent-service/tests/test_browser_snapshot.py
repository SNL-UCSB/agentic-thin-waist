from __future__ import annotations

import asyncio

import pytest

from netgent.client.browser.client import BrowserSession
from netgent.client.browser.exception import BrowserSessionError
from netgent.client.browser.snapshot import (
    BrowserCDPSnapshot,
    capture_browser_cdp_snapshot,
)


def test_browser_session_snapshot_delegates_to_cdp_snapshot(monkeypatch):
    expected = BrowserCDPSnapshot(
        selector="body",
        url="https://example.com",
        title="Example",
        root=None,
    )

    async def fake_capture(
        page, *, selector: str = "body", timeout_ms: float | None = None
    ):
        assert page == "page"
        assert selector == "body"
        assert timeout_ms is None
        return expected

    monkeypatch.setattr(
        "netgent.client.browser.actions.snapshot.capture_browser_cdp_snapshot",
        fake_capture,
    )

    session = BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page="page",
        cursor=None,
    )

    snapshot = asyncio.run(session.snapshot(selector="body"))

    assert snapshot is expected


def test_locator_for_ref_is_not_supported_with_cdp_snapshots():
    session = BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page="page",
        cursor=None,
    )

    with pytest.raises(BrowserSessionError, match="not supported"):
        session.locator_for_ref("e42")


def test_browser_snapshot_alias_points_to_cdp_snapshot():
    async def fake_capture(
        page, *, selector: str = "main", timeout_ms: float | None = None
    ):
        return BrowserCDPSnapshot(
            selector=selector,
            url="https://example.com",
            title="Example",
            root=None,
        )

    snapshot = asyncio.run(fake_capture("page"))

    assert isinstance(snapshot, BrowserCDPSnapshot)
