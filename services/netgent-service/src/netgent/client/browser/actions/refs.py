from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from netgent.client.browser.exception import BrowserSessionError
from netgent.client.browser.human_cursor import ORIGIN
from netgent.client.browser.snapshot import BrowserCDPSnapshot, BrowserCDPSnapshotNode

if TYPE_CHECKING:
    from netgent.client.browser.client import BrowserSession


async def click(
    session: BrowserSession,
    *,
    ref: str | None = None,
    selector: str | None = None,
    snapshot: BrowserCDPSnapshot | None = None,
    button: str = "left",
    click_count: int = 1,
) -> Any:
    if ref is not None:
        return await click_ref(
            session,
            ref,
            snapshot=snapshot,
            button=button,
            click_count=click_count,
        )
    if selector is None:
        raise BrowserSessionError("click requires either ref or selector")

    locator = session.page.locator(selector).first
    await locator.click(button=button, click_count=click_count)
    return selector


async def input_text(
    session: BrowserSession,
    text: str,
    *,
    ref: str | None = None,
    selector: str | None = None,
    snapshot: BrowserCDPSnapshot | None = None,
    clear: bool = True,
    delay_ms: float = 50,
    press_enter: bool = False,
) -> Any:
    if ref is not None:
        return await type_ref(
            session,
            ref,
            text,
            snapshot=snapshot,
            clear=clear,
            delay_ms=delay_ms,
            press_enter=press_enter,
        )
    if selector is None:
        raise BrowserSessionError("input requires either ref or selector")

    locator = session.page.locator(selector).first
    await locator.click()
    if clear:
        try:
            await locator.fill("")
        except Exception:
            modifier = "Meta" if _is_macos() else "Control"
            await session.page.keyboard.press(f"{modifier}+A")
            await session.page.keyboard.press("Backspace")
    await locator.type(text, delay=delay_ms)
    if press_enter:
        await session.page.keyboard.press("Enter")
    return selector


async def scroll(
    session: BrowserSession,
    *,
    delta_x: float = 0,
    delta_y: float = 0,
    ref: str | None = None,
    snapshot: BrowserCDPSnapshot | None = None,
    align: str = "center",
) -> Any:
    if ref is not None:
        return await scroll_ref(session, ref, snapshot=snapshot, align=align)

    await session.page.mouse.wheel(delta_x, delta_y)
    return await scroll_metrics(session)


async def scroll_ref(
    session: BrowserSession,
    ref: str,
    *,
    snapshot: BrowserCDPSnapshot | None = None,
    align: str = "center",
) -> BrowserCDPSnapshotNode:
    node = node_for_ref(session, ref, snapshot=snapshot)
    bounds = node_bounds(node)
    metrics = await scroll_metrics(session)

    if align == "top":
        target_top = max(0.0, bounds.y - 80.0)
    elif align == "bottom":
        target_top = max(0.0, bounds.bottom - metrics["innerHeight"] + 80.0)
    else:
        target_top = max(0.0, bounds.center_y - metrics["innerHeight"] / 2)

    target_left = max(0.0, bounds.center_x - metrics["innerWidth"] / 2)
    await scroll_to(session, top=target_top, left=target_left)
    return node


async def click_ref(
    session: BrowserSession,
    ref: str,
    *,
    snapshot: BrowserCDPSnapshot | None = None,
    button: str = "left",
    click_count: int = 1,
) -> BrowserCDPSnapshotNode:
    node = await session.scroll_ref(ref, snapshot=snapshot)
    x, y = await session._viewport_point_for_ref(node, editable=False)

    if session.cursor is not None:
        await session.cursor.move_to(ORIGIN.__class__(x, y))
    else:
        await session.page.mouse.move(x, y)

    await session.page.mouse.click(x, y, button=button, click_count=click_count)
    return node


async def type_ref(
    session: BrowserSession,
    ref: str,
    text: str,
    *,
    snapshot: BrowserCDPSnapshot | None = None,
    clear: bool = True,
    delay_ms: float = 50,
    press_enter: bool = False,
) -> BrowserCDPSnapshotNode:
    node = await session.scroll_ref(ref, snapshot=snapshot)
    x, y = await session._viewport_point_for_ref(node, editable=True)

    if session.cursor is not None:
        await session.cursor.move_to(ORIGIN.__class__(x, y))
    else:
        await session.page.mouse.move(x, y)

    await session.page.mouse.click(x, y)
    await session.page.wait_for_timeout(100)

    if clear:
        modifier = "Meta" if _is_macos() else "Control"
        await session.page.keyboard.press(f"{modifier}+A")
        await session.page.keyboard.press("Backspace")

    await session.page.keyboard.type(text, delay=delay_ms)
    if press_enter:
        await session.page.keyboard.press("Enter")
    return node


def locator_for_ref(ref: str) -> Any:
    raise BrowserSessionError(
        f"locator_for_ref is not supported for CDP snapshots (ref={ref!r})"
    )


def node_for_ref(
    session: BrowserSession,
    ref: str,
    *,
    snapshot: BrowserCDPSnapshot | None = None,
) -> BrowserCDPSnapshotNode:
    active_snapshot = snapshot or session.last_snapshot
    if active_snapshot is None:
        raise BrowserSessionError(
            f"No snapshot is available for ref-based action {ref!r}"
        )
    node = active_snapshot.node_for_ref(ref)
    if node is None:
        raise BrowserSessionError(
            f"Ref {ref!r} was not found in the active CDP snapshot"
        )
    return node


def node_bounds(node: BrowserCDPSnapshotNode):
    if node.bounds is None or node.bounds.width <= 0 or node.bounds.height < 0:
        raise BrowserSessionError(f"Ref {node.ref!r} does not have actionable bounds")
    return node.bounds


async def viewport_point_for_ref(
    session: BrowserSession,
    node: BrowserCDPSnapshotNode,
    *,
    editable: bool,
) -> tuple[float, float]:
    bounds = node_bounds(node)
    metrics = await scroll_metrics(session)

    if editable and node.role in {"combobox", "searchbox", "textbox"}:
        page_x, page_y = bounds.point_at(x_ratio=0.12, y_ratio=0.5)
    else:
        page_x, page_y = bounds.point_at(x_ratio=0.5, y_ratio=0.5)

    viewport_x = page_x - metrics["scrollX"]
    viewport_y = page_y - metrics["scrollY"]
    return viewport_x, viewport_y


async def scroll_metrics(session: BrowserSession) -> dict[str, float]:
    return await session.page.evaluate(
        """() => ({
            scrollX: window.scrollX,
            scrollY: window.scrollY,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight
        })"""
    )


async def scroll_to(session: BrowserSession, *, top: float, left: float) -> None:
    await session.page.evaluate(
        """params => {
            window.scrollTo({
                top: params.top,
                left: params.left,
                behavior: 'auto'
            });
        }""",
        {"top": top, "left": left},
    )
    await session.page.wait_for_timeout(100)


def _is_macos() -> bool:
    return sys.platform == "darwin"
