from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from netgent.client.browser.client import BrowserSession


async def search(
    session: BrowserSession,
    query: str,
    *,
    search_url_template: str = "https://www.google.com/search?q={query}",
    wait_until: str = "domcontentloaded",
) -> str:
    url = search_url_template.format(query=quote_plus(query))
    await navigate(session, url, wait_until=wait_until)
    return session.page.url


async def navigate(
    session: BrowserSession,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
) -> str:
    await session.page.goto(url, wait_until=wait_until)
    return session.page.url


async def go_back(
    session: BrowserSession,
    *,
    wait_until: str = "domcontentloaded",
) -> str | None:
    response = await session.page.go_back(wait_until=wait_until)
    if response is None:
        return None
    return session.page.url


async def wait(session: BrowserSession, timeout_ms: float = 1_000) -> None:
    await session.page.wait_for_timeout(timeout_ms)
