from __future__ import annotations

import asyncio

import pytest

from netgent.client.browser.client import BrowserSession
from netgent.client.browser.exception import BrowserSnapshotError
from netgent.client.browser.snapshot import (
    BrowserCDPBox,
    BrowserCDPSnapshot,
    BrowserCDPSnapshotNode,
    capture_browser_cdp_screenshot,
    capture_browser_cdp_snapshot,
)

ONE_BY_ONE_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn4nR4AAAAASUVORK5CYII="


class FakeLocator:
    def __init__(self) -> None:
        self.wait_calls: list[tuple[str, float | None]] = []
        self.first = self

    async def wait_for(self, *, state: str, timeout: float | None = None) -> None:
        self.wait_calls.append((state, timeout))


class FakeCDPSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.detached = False
        self._box_models = {
            2: {"model": {"border": [0, 0, 400, 0, 400, 300, 0, 300]}},
            3: {"model": {"border": [12, 18, 312, 18, 312, 58, 12, 58]}},
            4: {"model": {"border": [24, 80, 144, 80, 144, 124, 24, 124]}},
        }

    async def send(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params))
        if method in {"Page.enable", "DOM.enable", "Accessibility.enable"}:
            return {}
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 1}}
        if method == "DOM.querySelector":
            return {"nodeId": 2}
        if method == "DOM.describeNode":
            return {
                "node": {
                    "nodeId": 2,
                    "backendNodeId": 2,
                    "children": [
                        {"nodeId": 3, "backendNodeId": 3, "children": []},
                        {"nodeId": 4, "backendNodeId": 4, "children": []},
                    ],
                }
            }
        if method == "Accessibility.getFullAXTree":
            return {
                "nodes": [
                    {
                        "nodeId": "ax2",
                        "backendDOMNodeId": 2,
                        "role": {"value": "main"},
                        "childIds": ["ax3", "ax4"],
                    },
                    {
                        "nodeId": "ax3",
                        "backendDOMNodeId": 3,
                        "role": {"value": "textbox"},
                        "name": {"value": "Search"},
                        "value": {"value": "Browserless"},
                        "properties": [{"name": "focused", "value": {"value": "true"}}],
                    },
                    {
                        "nodeId": "ax4",
                        "backendDOMNodeId": 4,
                        "role": {"value": "button"},
                        "name": {"value": "Submit"},
                    },
                ]
            }
        if method == "DOM.getBoxModel":
            return self._box_models[params["backendNodeId"]]
        if method == "Page.getLayoutMetrics":
            return {
                "cssVisualViewport": {
                    "pageX": 0,
                    "pageY": 0,
                    "clientWidth": 400,
                    "clientHeight": 300,
                },
                "cssContentSize": {"width": 400, "height": 1200},
            }
        if method == "Page.captureScreenshot":
            return {"data": ONE_BY_ONE_PNG_BASE64}
        raise AssertionError(f"Unexpected CDP method: {method}")

    async def detach(self) -> None:
        self.detached = True


class FakeContext:
    def __init__(self, cdp: FakeCDPSession) -> None:
        self._cdp = cdp

    async def new_cdp_session(self, page) -> FakeCDPSession:
        return self._cdp


class FakePage:
    def __init__(self, cdp: FakeCDPSession) -> None:
        self.url = "https://example.com/search"
        self.context = FakeContext(cdp)
        self._locator = FakeLocator()

    def locator(self, selector: str) -> FakeLocator:
        assert selector == "main"
        return self._locator

    async def title(self) -> str:
        return "Search"


class FakeMouse:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []
        self.clicks: list[dict] = []

    async def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    async def click(
        self, x: float, y: float, *, button: str = "left", click_count: int = 1
    ) -> None:
        self.clicks.append(
            {"x": x, "y": y, "button": button, "click_count": click_count}
        )


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []
        self.typed: list[tuple[str, float]] = []

    async def press(self, key: str) -> None:
        self.presses.append(key)

    async def type(self, text: str, delay: float = 0) -> None:
        self.typed.append((text, delay))


class FakeActionPage:
    def __init__(self) -> None:
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.scroll_x = 0.0
        self.scroll_y = 0.0
        self.waits: list[float] = []

    async def evaluate(self, script: str, arg=None):
        if "window.scrollTo" in script:
            self.scroll_x = float(arg["left"])
            self.scroll_y = float(arg["top"])
            return None
        return {
            "scrollX": self.scroll_x,
            "scrollY": self.scroll_y,
            "innerWidth": 1280.0,
            "innerHeight": 720.0,
        }

    async def wait_for_timeout(self, delay_ms: float) -> None:
        self.waits.append(delay_ms)


def make_action_snapshot() -> BrowserCDPSnapshot:
    root = BrowserCDPSnapshotNode(
        ref="e1",
        role="main",
        bounds=BrowserCDPBox(x=0, y=0, width=1280, height=2000),
        children=(
            BrowserCDPSnapshotNode(
                ref="e25",
                role="combobox",
                name="Search",
                bounds=BrowserCDPBox(x=420, y=16, width=515, height=24),
            ),
            BrowserCDPSnapshotNode(
                ref="e223",
                role="button",
                name="Share",
                bounds=BrowserCDPBox(x=760, y=1200, width=92, height=36),
            ),
        ),
    )
    return BrowserCDPSnapshot.from_root(
        selector="body",
        url="https://example.com",
        title="Example",
        generated_at="2026-03-25T00:00:00Z",
        root=root,
    )


def test_capture_browser_cdp_snapshot_builds_ref_tree_without_dom_markers():
    cdp = FakeCDPSession()
    page = FakePage(cdp)

    snapshot = asyncio.run(
        capture_browser_cdp_snapshot(
            page,
            selector="main",
            timeout_ms=900,
        )
    )

    assert snapshot.selector == "main"
    assert snapshot.title == "Search"
    assert list(snapshot.refs) == ["e1", "e2", "e3"]
    assert snapshot.node_for_ref("e2").role == "textbox"
    assert snapshot.markdown == (
        '- main [ref=e1 bounds={"x": 0.0, "y": 0.0, "width": 400.0, "height": 300.0}]\n'
        '  - textbox "Search" [ref=e2 value="Browserless" bounds={"x": 12.0, "y": 18.0, "width": 300.0, "height": 40.0}]\n'
        '  - button "Submit" [ref=e3 bounds={"x": 24.0, "y": 80.0, "width": 120.0, "height": 44.0}]'
    )
    assert page._locator.wait_calls == [("attached", 900)]
    assert ("Page.captureScreenshot", None) not in cdp.calls
    assert cdp.detached is True


def test_capture_browser_cdp_screenshot_returns_annotation_overlay():
    cdp = FakeCDPSession()
    page = FakePage(cdp)

    screenshot = asyncio.run(
        capture_browser_cdp_screenshot(
            page,
            selector="main",
            timeout_ms=1200,
        )
    )

    assert screenshot.width == 1
    assert screenshot.height == 1
    assert len(screenshot.annotations) == 2
    assert screenshot.annotations[0].label == "1"
    assert screenshot.annotated_image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert screenshot.annotated_image_base64
    assert "Page.captureScreenshot" in [method for method, _ in cdp.calls]


def test_browser_session_snapshot_delegates_to_page():
    cdp = FakeCDPSession()
    page = FakePage(cdp)
    session = BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page=page,
        cursor=None,
    )

    snapshot = asyncio.run(session.snapshot(selector="main"))

    assert snapshot.root is not None
    assert snapshot.root.role == "main"


def test_capture_browser_cdp_snapshot_wraps_failures():
    class FailingCDP(FakeCDPSession):
        async def send(self, method: str, params: dict | None = None) -> dict:
            if method == "DOM.querySelector":
                raise RuntimeError("boom")
            return await super().send(method, params)

    with pytest.raises(
        BrowserSnapshotError, match="Unable to capture CDP browser snapshot"
    ):
        asyncio.run(
            capture_browser_cdp_snapshot(FakePage(FailingCDP()), selector="main")
        )


def test_browser_session_click_ref_scrolls_then_clicks_center():
    page = FakeActionPage()
    session = BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page=page,
        cursor=None,
        last_snapshot=make_action_snapshot(),
    )

    node = asyncio.run(session.click_ref("e223"))

    assert node.ref == "e223"
    assert page.scroll_y > 0
    assert page.mouse.clicks[0]["button"] == "left"
    assert round(page.mouse.clicks[0]["x"], 2) == 640.0
    assert round(page.mouse.clicks[0]["y"], 2) == 360.0


def test_browser_session_type_ref_uses_editable_bias_for_combobox():
    page = FakeActionPage()
    session = BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page=page,
        cursor=None,
        last_snapshot=make_action_snapshot(),
    )

    node = asyncio.run(session.type_ref("e25", "browser-use", press_enter=True))

    assert node.role == "combobox"
    assert page.mouse.clicks[0]["x"] < 500
    assert page.keyboard.presses[:2] == ["Meta+A", "Backspace"]
    assert page.keyboard.typed == [("browser-use", 50)]
    assert page.keyboard.presses[-1] == "Enter"
