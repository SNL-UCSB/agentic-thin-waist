from __future__ import annotations

import asyncio

from netgent.client.browser.client import (
    BrowserDropdownOption,
    BrowserFindTextResult,
    BrowserSession,
)


class FakeMouse:
    def __init__(self) -> None:
        self.wheels: list[tuple[float, float]] = []

    async def wheel(self, dx: float, dy: float) -> None:
        self.wheels.append((dx, dy))


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []

    async def press(self, key: str) -> None:
        self.presses.append(key)


class FakeTextNode:
    def __init__(self, text: str, visible: bool = True) -> None:
        self._text = text
        self._visible = visible

    async def is_visible(self) -> bool:
        return self._visible

    async def inner_text(self) -> str:
        return self._text


class FakeTextLocator:
    def __init__(self, texts: list[str]) -> None:
        self._nodes = [FakeTextNode(text) for text in texts]

    async def count(self) -> int:
        return len(self._nodes)

    def nth(self, index: int) -> FakeTextNode:
        return self._nodes[index]


class FakeLocator:
    def __init__(self) -> None:
        self.first = self
        self.clicked = False
        self.filled: list[str] = []
        self.typed: list[tuple[str, float]] = []
        self.selected_kwargs: list[dict] = []

    async def click(self, **kwargs) -> None:
        self.clicked = True

    async def fill(self, value: str) -> None:
        self.filled.append(value)

    async def type(self, text: str, delay: float = 0) -> None:
        self.typed.append((text, delay))

    async def select_option(self, **kwargs):
        self.selected_kwargs.append(kwargs)
        return ["selected"]

    async def evaluate(self, script: str):
        if "outerHTML" in script:
            return "<div>hello</div>"
        return [
            {
                "label": "First",
                "value": "first",
                "selected": True,
                "disabled": False,
            }
        ]

    async def inner_text(self) -> str:
        return "hello world"

    async def wait_for(self, *, state: str, timeout: float | None = None) -> None:
        return None


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com"
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.goto_calls: list[tuple[str, str]] = []
        self.go_back_calls: list[str] = []
        self.waits: list[float] = []
        self._locator = FakeLocator()
        self._text_locator = FakeTextLocator(["hello world", "hello again"])
        self._active_options = [
            {
                "label": "One",
                "value": "one",
                "selected": False,
                "disabled": False,
            }
        ]

    def locator(self, selector: str) -> FakeLocator:
        return self._locator

    def get_by_text(self, text: str, exact: bool = False) -> FakeTextLocator:
        return self._text_locator

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        self.goto_calls.append((url, wait_until))
        self.url = url

    async def go_back(self, wait_until: str = "domcontentloaded"):
        self.go_back_calls.append(wait_until)
        self.url = "https://example.com/back"
        return object()

    async def wait_for_timeout(self, timeout_ms: float) -> None:
        self.waits.append(timeout_ms)

    async def evaluate(self, expression: str, arg=None):
        if "window.scrollTo" in expression:
            return None
        if (
            "document.activeElement" in expression
            and "querySelectorAll('[role=\"option\"]')" in expression
        ):
            return self._active_options
        if "document.activeElement" in expression and "option.click()" in expression:
            return "one"
        if "return {" in expression or "scrollX" in expression:
            return {"scrollX": 0, "scrollY": 0, "innerWidth": 1280, "innerHeight": 720}
        return {"ok": True, "arg": arg}


def make_session() -> BrowserSession:
    return BrowserSession(
        playwright=None,
        browser=None,
        context=None,
        page=FakePage(),
        cursor=None,
    )


def test_navigation_search_and_wait_actions():
    session = make_session()

    search_url = asyncio.run(session.search("browser use"))
    navigated_url = asyncio.run(session.navigate("https://example.com/docs"))
    back_url = asyncio.run(session.go_back())
    asyncio.run(session.wait(250))

    assert "google.com/search?q=browser+use" in search_url
    assert navigated_url == "https://example.com/docs"
    assert back_url == "https://example.com/back"
    assert session.page.waits == [250]


def test_selector_actions_and_extract_helpers():
    session = make_session()

    asyncio.run(session.click(selector="#submit"))
    asyncio.run(session.input("hello", selector="#search", press_enter=True))
    find_result = asyncio.run(session.find_text("hello"))
    extract_text = asyncio.run(session.extract(selector="main", mode="text"))
    extract_html = asyncio.run(session.extract(selector="main", mode="html"))
    eval_result = asyncio.run(session.evaluate("() => ({ ok: true })"))
    asyncio.run(session.send_keys(["Meta+A", "Backspace"]))
    asyncio.run(session.scroll(delta_y=300))

    assert session.page._locator.clicked is True
    assert session.page._locator.filled == [""]
    assert session.page._locator.typed == [("hello", 50)]
    assert isinstance(find_result, BrowserFindTextResult)
    assert find_result.count == 2
    assert extract_text == "hello world"
    assert extract_html == "<div>hello</div>"
    assert eval_result["ok"] is True
    assert session.page.keyboard.presses[-3:] == ["Enter", "Meta+A", "Backspace"]
    assert session.page.mouse.wheels == [(0, 300)]


def test_dropdown_helpers():
    session = make_session()

    options = asyncio.run(session.dropdown_options(selector="select"))
    selected = asyncio.run(session.select_dropdown(selector="select", value="first"))

    assert options == (
        BrowserDropdownOption(
            label="First",
            value="first",
            selected=True,
            disabled=False,
        ),
    )
    assert selected == ["selected"]
