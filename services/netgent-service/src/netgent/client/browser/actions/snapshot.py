from __future__ import annotations

from typing import TYPE_CHECKING

from netgent.client.browser.snapshot import (
    BrowserCDPScreenshot,
    BrowserCDPSnapshot,
    capture_browser_cdp_screenshot,
    capture_browser_cdp_snapshot,
)

if TYPE_CHECKING:
    from netgent.client.browser.client import BrowserSession


async def snapshot(
    session: BrowserSession,
    *,
    selector: str = "body",
    include_hidden: bool = False,
    timeout_ms: float | None = None,
) -> BrowserCDPSnapshot:
    _ = include_hidden
    captured = await capture_browser_cdp_snapshot(
        session.page,
        selector=selector,
        timeout_ms=timeout_ms,
    )
    session.last_snapshot = captured
    return captured


async def screenshot(
    session: BrowserSession,
    *,
    selector: str = "body",
    full_page: bool = False,
    timeout_ms: float | None = None,
) -> BrowserCDPScreenshot:
    captured = await capture_browser_cdp_screenshot(
        session.page,
        selector=selector,
        full_page=full_page,
        timeout_ms=timeout_ms,
    )
    session.last_snapshot = captured.snapshot
    return captured
