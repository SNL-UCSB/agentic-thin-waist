from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from pydantic import BaseModel, ConfigDict, Field

from netgent.client.browser.actions import extract as extract_actions
from netgent.client.browser.actions import navigation as navigation_actions
from netgent.client.browser.actions import refs as ref_actions
from netgent.client.browser.actions import snapshot as snapshot_actions
from netgent.client.browser.exception import (
    BrowserConnectionError,
    BrowserSessionError,
)
from netgent.client.browser.human_cursor import ORIGIN, create_cursor
from netgent.client.browser.models import (
    BrowserDropdownOption,
    BrowserFindTextResult,
    BrowserViewport,
    StealthProfile,
)
from netgent.client.browser.snapshot import (
    BrowserCDPScreenshot,
    BrowserCDPSnapshot as BrowserSnapshot,
    BrowserCDPSnapshot,
    BrowserCDPSnapshotNode,
)


@dataclass(slots=True)
class BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    cursor: Any | None = None
    last_snapshot: BrowserCDPSnapshot | None = None

    async def close(self) -> None:
        if self.cursor is not None:
            try:
                self.cursor.toggle_random_move(False)
            except Exception:
                pass
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()

    async def __aenter__(self) -> BrowserSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def snapshot(
        self,
        *,
        selector: str = "body",
        include_hidden: bool = False,
        timeout_ms: float | None = None,
    ) -> BrowserSnapshot:
        return await snapshot_actions.snapshot(
            self,
            selector=selector,
            include_hidden=include_hidden,
            timeout_ms=timeout_ms,
        )

    async def screenshot(
        self,
        *,
        selector: str = "body",
        full_page: bool = False,
        timeout_ms: float | None = None,
    ) -> BrowserCDPScreenshot:
        return await snapshot_actions.screenshot(
            self,
            selector=selector,
            full_page=full_page,
            timeout_ms=timeout_ms,
        )

    async def search(
        self,
        query: str,
        *,
        search_url_template: str = "https://www.google.com/search?q={query}",
        wait_until: str = "domcontentloaded",
    ) -> str:
        return await navigation_actions.search(
            self,
            query,
            search_url_template=search_url_template,
            wait_until=wait_until,
        )

    async def navigate(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
    ) -> str:
        return await navigation_actions.navigate(self, url, wait_until=wait_until)

    async def go_back(self, *, wait_until: str = "domcontentloaded") -> str | None:
        return await navigation_actions.go_back(self, wait_until=wait_until)

    async def wait(self, timeout_ms: float = 1_000) -> None:
        await navigation_actions.wait(self, timeout_ms=timeout_ms)

    async def click(
        self,
        *,
        ref: str | None = None,
        selector: str | None = None,
        snapshot: BrowserCDPSnapshot | None = None,
        button: str = "left",
        click_count: int = 1,
    ) -> Any:
        return await ref_actions.click(
            self,
            ref=ref,
            selector=selector,
            snapshot=snapshot,
            button=button,
            click_count=click_count,
        )

    async def input(
        self,
        text: str,
        *,
        ref: str | None = None,
        selector: str | None = None,
        snapshot: BrowserCDPSnapshot | None = None,
        clear: bool = True,
        delay_ms: float = 50,
        press_enter: bool = False,
    ) -> Any:
        return await ref_actions.input_text(
            self,
            text,
            ref=ref,
            selector=selector,
            snapshot=snapshot,
            clear=clear,
            delay_ms=delay_ms,
            press_enter=press_enter,
        )

    async def scroll(
        self,
        *,
        delta_x: float = 0,
        delta_y: float = 0,
        ref: str | None = None,
        snapshot: BrowserCDPSnapshot | None = None,
        align: str = "center",
    ) -> Any:
        return await ref_actions.scroll(
            self,
            delta_x=delta_x,
            delta_y=delta_y,
            ref=ref,
            snapshot=snapshot,
            align=align,
        )

    async def find_text(
        self,
        text: str,
        *,
        exact: bool = False,
    ) -> BrowserFindTextResult:
        return await extract_actions.find_text(self, text, exact=exact)

    async def send_keys(self, keys: str | tuple[str, ...] | list[str]) -> None:
        await extract_actions.send_keys(self, keys)

    async def evaluate(self, expression: str, arg: Any | None = None) -> Any:
        return await extract_actions.evaluate(self, expression, arg)

    async def dropdown_options(
        self,
        *,
        ref: str | None = None,
        selector: str | None = None,
        snapshot: BrowserCDPSnapshot | None = None,
    ) -> tuple[BrowserDropdownOption, ...]:
        return await extract_actions.dropdown_options(
            self,
            ref=ref,
            selector=selector,
            snapshot=snapshot,
        )

    async def select_dropdown(
        self,
        *,
        ref: str | None = None,
        selector: str | None = None,
        label: str | None = None,
        value: str | None = None,
        index: int | None = None,
        snapshot: BrowserCDPSnapshot | None = None,
    ) -> Any:
        return await extract_actions.select_dropdown(
            self,
            ref=ref,
            selector=selector,
            label=label,
            value=value,
            index=index,
            snapshot=snapshot,
        )

    async def extract(
        self,
        *,
        selector: str = "body",
        mode: str = "text",
        timeout_ms: float | None = None,
    ) -> Any:
        return await extract_actions.extract(
            self,
            selector=selector,
            mode=mode,
            timeout_ms=timeout_ms,
        )

    async def scroll_ref(
        self,
        ref: str,
        *,
        snapshot: BrowserCDPSnapshot | None = None,
        align: str = "center",
    ) -> BrowserCDPSnapshotNode:
        return await ref_actions.scroll_ref(
            self,
            ref,
            snapshot=snapshot,
            align=align,
        )

    async def click_ref(
        self,
        ref: str,
        *,
        snapshot: BrowserCDPSnapshot | None = None,
        button: str = "left",
        click_count: int = 1,
    ) -> BrowserCDPSnapshotNode:
        return await ref_actions.click_ref(
            self,
            ref,
            snapshot=snapshot,
            button=button,
            click_count=click_count,
        )

    async def type_ref(
        self,
        ref: str,
        text: str,
        *,
        snapshot: BrowserCDPSnapshot | None = None,
        clear: bool = True,
        delay_ms: float = 50,
        press_enter: bool = False,
    ) -> BrowserCDPSnapshotNode:
        return await ref_actions.type_ref(
            self,
            ref,
            text,
            snapshot=snapshot,
            clear=clear,
            delay_ms=delay_ms,
            press_enter=press_enter,
        )

    def locator_for_ref(self, ref: str) -> Any:
        return ref_actions.locator_for_ref(ref)

    def _node_for_ref(
        self,
        ref: str,
        *,
        snapshot: BrowserCDPSnapshot | None = None,
    ) -> BrowserCDPSnapshotNode:
        return ref_actions.node_for_ref(self, ref, snapshot=snapshot)

    @staticmethod
    def _node_bounds(node: BrowserCDPSnapshotNode):
        return ref_actions.node_bounds(node)

    async def _viewport_point_for_ref(
        self,
        node: BrowserCDPSnapshotNode,
        *,
        editable: bool,
    ) -> tuple[float, float]:
        return await ref_actions.viewport_point_for_ref(
            self,
            node,
            editable=editable,
        )

    async def _scroll_metrics(self) -> dict[str, float]:
        return await ref_actions.scroll_metrics(self)

    async def _scroll_to(self, *, top: float, left: float) -> None:
        await ref_actions.scroll_to(self, top=top, left=left)

    def _is_macos(self) -> bool:
        return sys.platform == "darwin"


class BrowserClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cdp_ws_endpoint: str = "ws://browserless:3000"
    default_timeout_ms: int = 30_000
    cursor_visible: bool = False
    cursor_random_moves: bool = False
    stealth_profile: StealthProfile = Field(default_factory=StealthProfile)
    connect_kwargs: dict[str, Any] = Field(default_factory=dict)

    async def open(self) -> BrowserSession:
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.connect_over_cdp(
                self.cdp_ws_endpoint,
                timeout=self.default_timeout_ms,
                **self.connect_kwargs,
            )
        except Exception as exc:
            await playwright.stop()
            raise BrowserConnectionError(
                f"Unable to connect to CDP endpoint '{self.cdp_ws_endpoint}'"
            ) from exc

        try:
            context = await self._create_context(browser)
            await self._apply_stealth(context)
            page = await context.new_page()
            page.set_default_timeout(self.default_timeout_ms)

            cursor = await self._create_cursor(page)
            return BrowserSession(
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                cursor=cursor,
            )
        except Exception:
            await browser.close()
            await playwright.stop()
            raise

    async def _create_context(self, browser: Browser) -> BrowserContext:
        context_kwargs = self.stealth_profile.context_kwargs()

        if context_kwargs:
            try:
                return await browser.new_context(**context_kwargs)
            except Exception as exc:
                raise BrowserSessionError(
                    "Unable to create a browser context with the requested stealth settings"
                ) from exc

        if browser.contexts:
            return browser.contexts[0]
        return await browser.new_context()

    async def _apply_stealth(self, context: BrowserContext) -> None:
        for script in self.stealth_profile.init_scripts():
            await context.add_init_script(script)

    async def _create_cursor(self, page: Page) -> Any:
        cursor = create_cursor(
            page,
            start=ORIGIN,
            perform_random_moves=self.cursor_random_moves,
            visible=self.cursor_visible,
        )
        await cursor.start()
        return cursor
