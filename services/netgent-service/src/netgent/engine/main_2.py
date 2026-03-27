from __future__ import annotations

import base64
import os
import tempfile
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

load_dotenv()


class NetGentExecutor:
    def __init__(self, workflow_id: str | None = None) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.browserless_ws_endpoint = os.getenv(
            "BROWSERLESS_WS_ENDPOINT",
            "ws://browserless:3000/chromium/playwright",
        )
        self.timeout_seconds = int(os.getenv("NETGENT_TIMEOUT_DEFAULT", "30"))
        self._playwright_manager = None
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.har_path: str | None = None

        if workflow_id:
            har_fd, har_path = tempfile.mkstemp(
                prefix=f"netgent-{workflow_id}-",
                suffix=".har",
            )
            os.close(har_fd)
            self.har_path = har_path

    def connect_browser(self) -> Browser:
        """Connect Playwright to the remote Browserless instance."""

        if self.browser is not None:
            return self.browser

        self._playwright_manager = sync_playwright()
        self._playwright = self._playwright_manager.start()
        self.browser = self._playwright.chromium.connect(
            ws_endpoint=self.browserless_ws_endpoint,
            timeout=self.timeout_seconds * 1000,
        )
        return self.browser

    def _ensure_page(self) -> Page:
        browser = self.connect_browser()
        if self.context is None:
            context_kwargs: dict[str, Any] = {}
            if self.har_path:
                context_kwargs["record_har_path"] = self.har_path
                context_kwargs["record_har_mode"] = "full"
            self.context = browser.new_context(**context_kwargs)

        if self.page is None:
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout_seconds * 1000)

        return self.page

    def _accept_youtube_consent(self, page: Page) -> None:
        consent_buttons = (
            page.get_by_role("button", name="Accept all"),
            page.get_by_role("button", name="I agree"),
        )
        for button in consent_buttons:
            try:
                if button.is_visible(timeout=2000):
                    button.click()
                    return
            except Exception:
                continue

    def _capture_screenshot(self, page: Page, action: str) -> dict[str, str]:
        screenshot_bytes = page.screenshot(full_page=True)
        image_base64 = base64.b64encode(screenshot_bytes).decode("ascii")
        return {
            "action": action,
            "image_base64": image_base64,
        }

    def _get_youtube_playback_state(self, page: Page) -> dict[str, Any]:
        page.wait_for_selector("video", state="attached")
        page.wait_for_timeout(2000)

        return page.evaluate(
            """() => {
                const video = document.querySelector('video');
                if (!video) {
                    return {
                        has_video_element: false,
                        is_playing: false,
                        is_paused: true,
                        current_time_seconds: 0,
                    };
                }

                return {
                    has_video_element: true,
                    is_playing: !video.paused && !video.ended && video.currentTime > 0,
                    is_paused: video.paused,
                    current_time_seconds: Number(video.currentTime.toFixed(2)),
                };
            }"""
        )

    def play_youtube(
        self, search_query: str = "Hello World"
    ) -> tuple[Page, list[dict[str, str]], dict[str, Any]]:
        page = self._ensure_page()
        screenshots: list[dict[str, str]] = []

        page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        screenshots.append(self._capture_screenshot(page, "01_home_loaded"))

        self._accept_youtube_consent(page)
        screenshots.append(self._capture_screenshot(page, "02_consent_handled"))

        page.locator('input[name="search_query"]').fill(search_query)
        screenshots.append(self._capture_screenshot(page, "03_search_query_filled"))

        page.locator('input[name="search_query"]').press("Enter")
        page.wait_for_url("**/results?search_query=**")
        screenshots.append(self._capture_screenshot(page, "04_search_results_loaded"))

        first_video = page.locator("ytd-video-renderer a#video-title").first
        first_video.wait_for(state="visible")
        first_video.click()
        page.wait_for_url("**/watch?**")
        screenshots.append(self._capture_screenshot(page, "05_video_opened"))
        playback = self._get_youtube_playback_state(page)
        screenshots.append(self._capture_screenshot(page, "06_playback_checked"))

        return page, screenshots, playback

    def execute_youtube_workflow(
        self, search_query: str = "Hello World"
    ) -> dict[str, Any]:
        page, screenshots, playback = self.play_youtube(search_query=search_query)
        return {
            "search_query": search_query,
            "page_url": page.url,
            "title": page.title(),
            "playback": playback,
            "screenshots": screenshots,
        }

    def close(self) -> str | None:
        if self.page is not None:
            self.page.close()
            self.page = None

        if self.context is not None:
            self.context.close()
            self.context = None

        if self.browser is not None:
            self.browser.close()
            self.browser = None

        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
            self._playwright_manager = None

        return (
            self.har_path if self.har_path and os.path.exists(self.har_path) else None
        )

    def execute(self) -> Browser:
        return self.connect_browser()

    def __enter__(self) -> "NetGentExecutor":
        self.connect_browser()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
