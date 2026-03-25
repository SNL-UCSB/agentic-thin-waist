"""Main cursor implementation – Python port of spoof.ts from human-cursor."""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Literal, Optional, Union

from playwright.async_api import ElementHandle, Locator, Page

from .calculate_and_randomize import generate_random_curve_parameters
from .human_curve_generator import HumanizeMouseTrajectory
from .math_utils import ORIGIN, TimedVector, Vector, clamp, scale
from .mouse_helper import install_mouse_helper_async

logger = logging.getLogger("human-cursor")

# ──────────────────────────────── types ────────────────────────────────


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass
class BoxOptions:
    padding_percentage: float = 0
    destination: Optional[Vector] = None


@dataclass
class GetElementOptions:
    wait_for_selector: Optional[int] = None


@dataclass
class ScrollOptions:
    scroll_speed: int = 100
    scroll_delay: int = 200


@dataclass
class ScrollIntoViewOptions(ScrollOptions, GetElementOptions):
    in_viewport_margin: int = 0


@dataclass
class MoveOptions(BoxOptions, ScrollIntoViewOptions):
    move_delay: int = 0
    randomize_move_delay: bool = True
    max_tries: int = 10
    overshoot_threshold: int = 500
    spread_override: Optional[float] = None
    move_speed: Optional[float] = None
    use_timestamps: bool = False


@dataclass
class ClickOptions(MoveOptions):
    hesitate: int = 0
    wait_for_click: int = 0
    button: Literal["left", "right", "middle"] = "left"
    click_count: int = 1


@dataclass
class MoveToOptions:
    move_delay: int = 0
    randomize_move_delay: bool = True
    spread_override: Optional[float] = None
    move_speed: Optional[float] = None
    use_timestamps: bool = False


# ──────────────────────────── helpers ──────────────────────────────────


def _get_random_box_point(box: BoundingBox) -> Vector:
    x_off = (random.randint(20, 79)) / 100
    y_off = (random.randint(20, 79)) / 100
    return Vector(box.x + box.width * x_off, box.y + box.height * y_off)


def _intersects_element(vec: Vector, box: BoundingBox) -> bool:
    return (
        vec.x > box.x
        and vec.x <= box.x + box.width
        and vec.y > box.y
        and vec.y <= box.y + box.height
    )


async def get_random_page_point(page: Page) -> Vector:
    vp = page.viewport_size
    if vp is None:
        return Vector(0, 0)
    return _get_random_box_point(BoundingBox(0, 0, vp["width"], vp["height"]))


async def get_element_box(page: Page, element: ElementHandle) -> BoundingBox:
    try:
        bb = await element.bounding_box()
        if bb is None:
            raise RuntimeError("bounding_box returned None")
        return BoundingBox(**bb)
    except Exception:
        rect = await element.evaluate("el => el.getBoundingClientRect()")
        return BoundingBox(rect["x"], rect["y"], rect["width"], rect["height"])


async def _momentum_wheel_scroll(
    page: Page,
    x: float,
    y: float,
    duration: float = 600,
) -> None:
    """Momentum-based wheel scrolling with ease-out cubic for human-like behaviour."""
    start = time.monotonic()
    base_interval = 0.016  # ~16 ms

    while True:
        elapsed = time.monotonic() - start
        t = min(elapsed / (duration / 1000), 1.0)

        ease = 1 - (1 - t) ** 3

        target_x = x * ease
        target_y = y * ease

        prev_t = max(0, t - base_interval / (duration / 1000))
        prev_ease = 1 - (1 - prev_t) ** 3
        prev_target_x = x * prev_ease
        prev_target_y = y * prev_ease

        dx = target_x - prev_target_x
        dy = target_y - prev_target_y

        try:
            await page.mouse.wheel(dx, dy)
        except Exception:
            pass

        if t >= 1:
            break

        jitter = base_interval + (random.random() * 0.004 - 0.002)
        await asyncio.sleep(max(0, jitter))


# ──────────────────── path generation (internal) ──────────────────────


def _clamp_positive(vectors: list[Vector]) -> list[Vector]:
    return [Vector(max(0, v.x), max(0, v.y)) for v in vectors]


async def _path_with_human_curve(
    start: Vector,
    end: Vector,
    spread_override: Optional[float] = None,
) -> list[Vector]:
    params = generate_random_curve_parameters(start, end)

    ob_x = spread_override if spread_override is not None else params.offset_boundary_x
    ob_y = spread_override if spread_override is not None else params.offset_boundary_y

    curve = HumanizeMouseTrajectory(
        start,
        end,
        offset_boundary_x=ob_x,
        offset_boundary_y=ob_y,
        knots_count=params.knots_count,
        distortion_mean=params.distortion_mean,
        distortion_st_dev=params.distortion_st_dev,
        distortion_frequency=params.distortion_frequency,
        tweening=params.tween,
        target_points=params.target_points,
    )
    return _clamp_positive(curve.points)


# ──────────────────────────── GhostCursor ─────────────────────────────


class GhostCursor:
    """Human-like mouse cursor for Playwright (async API)."""

    def __init__(
        self,
        page: Page,
        start: Vector = ORIGIN,
        perform_random_moves: bool = False,
        visible: bool = False,
        *,
        default_move: Optional[MoveOptions] = None,
        default_move_to: Optional[MoveToOptions] = None,
        default_click: Optional[ClickOptions] = None,
        default_scroll: Optional[ScrollIntoViewOptions] = None,
        default_get_element: Optional[GetElementOptions] = None,
        default_random_move: Optional[MoveToOptions] = None,
    ) -> None:
        self._page = page
        self._previous = start.copy()
        self._moving = False
        self._random_move_task: Optional[asyncio.Task] = None

        self._default_move = default_move
        self._default_move_to = default_move_to
        self._default_click = default_click
        self._default_scroll = default_scroll
        self._default_get_element = default_get_element
        self._default_random_move = default_random_move

        self._visible = visible
        self._perform_random_moves = perform_random_moves

    async def __aenter__(self) -> GhostCursor:
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        self.toggle_random_move(False)

    async def start(self) -> None:
        """Initialise cursor position (and optional helpers)."""
        try:
            await self._page.mouse.move(self._previous.x, self._previous.y)
        except Exception:
            pass

        if self._visible:
            await install_mouse_helper_async(self._page)

        if self._perform_random_moves:
            self._start_random_moves()

    # ────────────── location ──────────────

    def get_location(self) -> Vector:
        return self._previous.copy()

    # ────────────── random move toggle ──────────────

    def toggle_random_move(self, enabled: bool) -> None:
        self._moving = not enabled
        if not enabled and self._random_move_task is not None:
            self._random_move_task.cancel()
            self._random_move_task = None

    # ────────────── trace path ──────────────

    async def _trace_path(
        self, vectors: list[Vector], abort_on_move: bool = False
    ) -> None:
        for v in vectors:
            try:
                if abort_on_move and self._moving:
                    return
                await self._page.mouse.move(v.x, v.y)
                self._previous = v
            except Exception:
                if self._page.is_closed():
                    return
                logger.warning("Could not move mouse")

    # ────────────── random moves ──────────────

    def _start_random_moves(self) -> None:
        loop = asyncio.get_event_loop()
        self._random_move_task = loop.create_task(self._random_move_loop())

    async def _random_move_loop(self) -> None:
        delay_ms = 2000
        if self._default_random_move and self._default_random_move.move_delay:
            delay_ms = self._default_random_move.move_delay
        try:
            while True:
                if not self._moving:
                    rand = await get_random_page_point(self._page)
                    pts = await _path_with_human_curve(self._previous, rand)
                    await self._trace_path(pts, abort_on_move=True)
                await asyncio.sleep(delay_ms / 1000 * random.random())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Stopping random mouse movements")

    # ────────────── get_element ──────────────

    async def get_element(
        self,
        selector: Union[str, ElementHandle, Locator],
        options: Optional[GetElementOptions] = None,
    ) -> ElementHandle:
        opts = options or self._default_get_element or GetElementOptions()

        if isinstance(selector, str):
            if selector.startswith("//") or selector.startswith("(//"):
                sel = f"xpath={selector}"
            else:
                sel = selector
            if opts.wait_for_selector is not None:
                await self._page.wait_for_selector(sel, timeout=opts.wait_for_selector)
            elem = await self._page.query_selector(sel)
            if elem is None:
                raise RuntimeError(
                    f'Could not find element with selector "{selector}". '
                    "Use wait_for_selector to wait for it."
                )
            return elem

        if isinstance(selector, Locator):
            if opts.wait_for_selector is not None:
                await selector.wait_for(timeout=opts.wait_for_selector)
            handle = await selector.element_handle()
            if handle is None:
                raise RuntimeError("Could not obtain ElementHandle from Locator")
            return handle

        return selector

    # ────────────── scroll helpers ──────────────

    async def scroll(
        self,
        delta: Vector,
        options: Optional[ScrollOptions] = None,
    ) -> None:
        """Scroll the page by *delta* pixels with momentum easing."""
        opts = options or self._default_scroll or ScrollOptions()
        speed = clamp(opts.scroll_speed, 1, 100)
        duration = scale(speed, (1, 100), (2000, 300))
        await _momentum_wheel_scroll(self._page, delta.x, delta.y, duration)
        await asyncio.sleep(opts.scroll_delay / 1000)

    async def scroll_to(
        self,
        destination: Union[str, Vector],
        options: Optional[ScrollOptions] = None,
    ) -> None:
        opts = options or self._default_scroll or ScrollOptions()
        info = await self._page.evaluate(
            """() => ({
                docHeight: document.body.scrollHeight,
                docWidth: document.body.scrollWidth,
                scrollTop: window.scrollY,
                scrollLeft: window.scrollX
            })"""
        )
        if isinstance(destination, str):
            mapping = {
                "top": Vector(0, 0),
                "bottom": Vector(0, info["docHeight"]),
                "left": Vector(0, 0),
                "right": Vector(info["docWidth"], 0),
            }
            to = mapping.get(destination, Vector(0, 0))
        else:
            to = destination

        dy = to.y - info["scrollTop"] if to.y else 0
        dx = to.x - info["scrollLeft"] if to.x else 0
        await self.scroll(Vector(dx, dy), opts)

    async def scroll_into_view(
        self,
        selector: Union[str, ElementHandle, Locator],
        options: Optional[ScrollIntoViewOptions] = None,
    ) -> None:
        opts = options or self._default_scroll or ScrollIntoViewOptions()

        elem = (
            selector
            if isinstance(selector, ElementHandle)
            else await self.get_element(
                selector,
                GetElementOptions(
                    wait_for_selector=(
                        opts.wait_for_selector
                        if isinstance(opts, ScrollIntoViewOptions)
                        else None
                    )
                ),
            )
        )

        info = await self._page.evaluate(
            """() => ({
                docHeight: document.body.scrollHeight,
                docWidth: document.body.scrollWidth,
                viewportHeight: window.innerHeight,
                viewportWidth: window.innerWidth,
                scrollTop: window.scrollY,
                scrollLeft: window.scrollX
            })"""
        )

        ebb = await get_element_box(self._page, elem)
        margin = (
            opts.in_viewport_margin if isinstance(opts, ScrollIntoViewOptions) else 0
        )

        elem_top = ebb.y - margin
        elem_left = ebb.x - margin
        elem_bottom = ebb.y + ebb.height + margin
        elem_right = ebb.x + ebb.width + margin

        # Clamp to document bounds
        doc_top = max(elem_top + info["scrollTop"], 0) - info["scrollTop"]
        doc_left = max(elem_left + info["scrollLeft"], 0) - info["scrollLeft"]
        doc_bottom = (
            min(elem_bottom + info["scrollTop"], info["docHeight"]) - info["scrollTop"]
        )
        doc_right = (
            min(elem_right + info["scrollLeft"], info["docWidth"]) - info["scrollLeft"]
        )

        in_viewport = (
            doc_top >= 0
            and doc_left >= 0
            and doc_bottom <= info["viewportHeight"]
            and doc_right <= info["viewportWidth"]
        )
        if in_viewport:
            return

        dy = 0.0
        dx = 0.0
        if doc_top < 0:
            dy = doc_top
        elif doc_bottom > info["viewportHeight"]:
            dy = doc_bottom - info["viewportHeight"]
        if doc_left < 0:
            dx = doc_left
        elif doc_right > info["viewportWidth"]:
            dx = doc_right - info["viewportWidth"]

        padding_y = min(abs(dy) * 0.1, 50) * (random.random() * 2 - 1)
        padding_x = min(abs(dx) * 0.1, 50) * (random.random() * 2 - 1)

        try:
            await self.scroll(Vector(dx + padding_x, dy + padding_y), opts)
        except Exception:
            logger.warning("Falling back to JS scrollIntoView")
            await elem.evaluate(
                "e => e.scrollIntoView({block:'center',behavior:'smooth'})"
            )

    # ────────────── move ──────────────

    async def move(
        self,
        selector: Union[str, ElementHandle, Locator],
        options: Optional[MoveOptions] = None,
    ) -> None:
        """Move the cursor to *selector* with human-like motion."""
        opts = options or self._default_move or MoveOptions()
        was_random = not self._moving

        async def _go(iteration: int) -> None:
            if iteration > opts.max_tries:
                raise RuntimeError("Could not mouse-over element within enough tries")

            self.toggle_random_move(False)

            elem = await self.get_element(
                selector, GetElementOptions(wait_for_selector=opts.wait_for_selector)
            )
            await self.scroll_into_view(
                elem,
                ScrollIntoViewOptions(
                    scroll_speed=opts.scroll_speed,
                    scroll_delay=opts.scroll_delay,
                    in_viewport_margin=(
                        opts.in_viewport_margin
                        if hasattr(opts, "in_viewport_margin")
                        else 0
                    ),
                ),
            )

            box = await get_element_box(self._page, elem)
            already_in = _intersects_element(self._previous, box)

            if opts.destination is not None:
                dest = Vector(box.x + opts.destination.x, box.y + opts.destination.y)
            elif already_in:
                dest = self._previous.copy()
            else:
                dest = _get_random_box_point(box)

            dist = math.sqrt(
                (dest.x - self._previous.x) ** 2 + (dest.y - self._previous.y) ** 2
            )
            if dist > 5:
                pts = await _path_with_human_curve(
                    self._previous, dest, opts.spread_override
                )
                await self._trace_path(pts)
            else:
                self._previous = dest

            self.toggle_random_move(True)

            new_box = await get_element_box(self._page, elem)
            if not _intersects_element(dest, new_box):
                await _go(iteration + 1)

        await _go(0)
        self.toggle_random_move(was_random)

        delay_ms = opts.move_delay * (
            random.random() if opts.randomize_move_delay else 1
        )
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    # ────────────── move_to ──────────────

    async def move_to(
        self,
        destination: Vector,
        options: Optional[MoveToOptions] = None,
    ) -> None:
        """Move the cursor to an absolute coordinate."""
        opts = options or self._default_move_to or MoveToOptions()
        was_random = not self._moving
        self.toggle_random_move(False)

        dist = math.sqrt(
            (destination.x - self._previous.x) ** 2
            + (destination.y - self._previous.y) ** 2
        )
        if dist > 5:
            pts = await _path_with_human_curve(
                self._previous, destination, opts.spread_override
            )
            await self._trace_path(pts)
        else:
            self._previous = destination

        self.toggle_random_move(was_random)

    # ────────────── click ──────────────

    async def click(
        self,
        selector: Optional[Union[str, ElementHandle, Locator]] = None,
        options: Optional[ClickOptions] = None,
    ) -> None:
        """Click on *selector* (or current position) with human-like motion."""
        opts = options or self._default_click or ClickOptions()
        was_random = not self._moving
        self.toggle_random_move(False)

        element_to_click: Optional[ElementHandle] = None

        if selector is not None:
            move_opts = MoveOptions(
                padding_percentage=opts.padding_percentage,
                destination=opts.destination,
                wait_for_selector=opts.wait_for_selector,
                scroll_speed=opts.scroll_speed,
                scroll_delay=opts.scroll_delay,
                move_delay=0,
                randomize_move_delay=False,
                max_tries=opts.max_tries,
                overshoot_threshold=opts.overshoot_threshold,
                spread_override=opts.spread_override,
                move_speed=opts.move_speed,
                use_timestamps=opts.use_timestamps,
            )
            await self.move(selector, move_opts)
            element_to_click = await self.get_element(selector)

        try:
            if opts.hesitate > 0:
                await asyncio.sleep(opts.hesitate / 1000)

            if element_to_click is not None:
                await element_to_click.click(
                    button=opts.button,
                    click_count=opts.click_count,
                    delay=opts.wait_for_click,
                )
        except Exception:
            logger.warning("Could not click mouse")

        delay_ms = opts.move_delay * (
            random.random() if opts.randomize_move_delay else 1
        )
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

        self.toggle_random_move(was_random)


# ─────────────────────── factory function ─────────────────────────────


def create_cursor(
    page: Page,
    start: Vector = ORIGIN,
    perform_random_moves: bool = False,
    visible: bool = False,
    **default_options,
) -> GhostCursor:
    """Create a :class:`GhostCursor` for *page* (async Playwright).

    Usage::

        cursor = create_cursor(page)
        await cursor.start()
        await cursor.click("#submit")
    """
    return GhostCursor(
        page,
        start=start,
        perform_random_moves=perform_random_moves,
        visible=visible,
        **default_options,
    )
