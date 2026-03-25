from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Page

from netgent.client.browser.exception import BrowserSnapshotError
from netgent.client.browser.snapshot.models import (
    BrowserCDPAnnotation,
    BrowserCDPBox,
    BrowserCDPScreenshot,
    BrowserCDPSnapshot,
    BrowserCDPSnapshotNode,
)

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
    }
)


async def capture_browser_cdp_snapshot(
    page: Page,
    *,
    selector: str = "body",
    timeout_ms: float | None = None,
) -> BrowserCDPSnapshot:
    locator = page.locator(selector).first
    try:
        await locator.wait_for(state="attached", timeout=timeout_ms)
        cdp = await page.context.new_cdp_session(page)
        try:
            await _enable_cdp_domains(cdp)
            root_node = await _resolve_selector_node(cdp, selector)
            return await _build_snapshot(page, cdp, selector, root_node)
        finally:
            await _detach_session(cdp)
    except Exception as exc:
        raise BrowserSnapshotError(
            f"Unable to capture CDP browser snapshot for selector '{selector}'"
        ) from exc


async def capture_browser_cdp_screenshot(
    page: Page,
    *,
    selector: str = "body",
    full_page: bool = False,
    timeout_ms: float | None = None,
) -> BrowserCDPScreenshot:
    locator = page.locator(selector).first
    try:
        await locator.wait_for(state="attached", timeout=timeout_ms)
        cdp = await page.context.new_cdp_session(page)
        try:
            await _enable_cdp_domains(cdp)
            root_node = await _resolve_selector_node(cdp, selector)
            snapshot = await _build_snapshot(page, cdp, selector, root_node)
            layout_metrics = await cdp.send("Page.getLayoutMetrics")
            screenshot_kwargs = {"format": "png", "fromSurface": True}
            clip = None

            if full_page:
                screenshot_kwargs["captureBeyondViewport"] = True
            elif (
                selector != "body"
                and snapshot.root
                and snapshot.root.bounds is not None
            ):
                root_bounds = snapshot.root.bounds
                clip = {
                    "x": root_bounds.x,
                    "y": root_bounds.y,
                    "width": root_bounds.width,
                    "height": root_bounds.height,
                    "scale": 1,
                }
                screenshot_kwargs["clip"] = clip

            payload = await cdp.send("Page.captureScreenshot", screenshot_kwargs)
            annotations = _build_annotations(
                snapshot=snapshot,
                layout_metrics=layout_metrics,
                full_page=full_page,
                clip=clip,
            )
            return BrowserCDPScreenshot.from_image_base64(
                selector=selector,
                url=page.url,
                title=await page.title(),
                generated_at=_timestamp(),
                image_base64=payload["data"],
                full_page=full_page,
                snapshot=snapshot,
                annotations=annotations,
            )
        finally:
            await _detach_session(cdp)
    except Exception as exc:
        raise BrowserSnapshotError(
            f"Unable to capture CDP browser screenshot for selector '{selector}'"
        ) from exc


async def annotate_browser_cdp_screenshot(
    page: Page,
    *,
    selector: str = "body",
    full_page: bool = False,
    timeout_ms: float | None = None,
) -> BrowserCDPScreenshot:
    return await capture_browser_cdp_screenshot(
        page,
        selector=selector,
        full_page=full_page,
        timeout_ms=timeout_ms,
    )


async def _enable_cdp_domains(cdp: Any) -> None:
    await cdp.send("Page.enable")
    await cdp.send("DOM.enable")
    await cdp.send("Accessibility.enable")


async def _detach_session(cdp: Any) -> None:
    detach = getattr(cdp, "detach", None)
    if detach is None:
        return
    try:
        await detach()
    except Exception:
        pass


async def _resolve_selector_node(cdp: Any, selector: str) -> dict[str, Any]:
    document = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
    root_node_id = document["root"]["nodeId"]
    result = await cdp.send(
        "DOM.querySelector",
        {"nodeId": root_node_id, "selector": selector},
    )
    node_id = result.get("nodeId", 0)
    if not node_id:
        raise BrowserSnapshotError(f"Unable to resolve selector '{selector}' via CDP")
    description = await cdp.send(
        "DOM.describeNode",
        {"nodeId": node_id, "depth": -1, "pierce": True},
    )
    return description["node"]


async def _build_snapshot(
    page: Page,
    cdp: Any,
    selector: str,
    dom_root: dict[str, Any],
) -> BrowserCDPSnapshot:
    backend_ids = _collect_backend_ids(dom_root)
    if not backend_ids:
        raise BrowserSnapshotError(f"Selector '{selector}' has no backend DOM nodes")

    ax_tree = await cdp.send("Accessibility.getFullAXTree")
    ax_nodes = ax_tree.get("nodes", [])
    ax_by_id = {node["nodeId"]: node for node in ax_nodes}

    root_backend_id = dom_root.get("backendNodeId")
    root_ax_node = _select_root_ax_node(ax_nodes, root_backend_id)
    if root_ax_node is None:
        raise BrowserSnapshotError(
            f"Unable to locate accessibility node for selector '{selector}'"
        )

    ref_state = {"next_ref": 0}
    box_cache: dict[int, BrowserCDPBox | None] = {}
    root = await _build_snapshot_node(
        cdp=cdp,
        ax_by_id=ax_by_id,
        ax_node=root_ax_node,
        backend_ids=backend_ids,
        root_backend_id=root_backend_id,
        box_cache=box_cache,
        ref_state=ref_state,
    )

    return BrowserCDPSnapshot.from_root(
        selector=selector,
        url=page.url,
        title=await page.title(),
        generated_at=_timestamp(),
        root=root,
    )


def _select_root_ax_node(
    ax_nodes: list[dict[str, Any]],
    root_backend_id: int | None,
) -> dict[str, Any] | None:
    if root_backend_id is None:
        return None

    for node in ax_nodes:
        if node.get("backendDOMNodeId") != root_backend_id:
            continue
        role = _ax_value(node.get("role"))
        if role and role != "none":
            return node

    for node in ax_nodes:
        if node.get("backendDOMNodeId") == root_backend_id:
            return node
    return None


async def _build_snapshot_node(
    *,
    cdp: Any,
    ax_by_id: dict[str, dict[str, Any]],
    ax_node: dict[str, Any],
    backend_ids: set[int],
    root_backend_id: int | None,
    box_cache: dict[int, BrowserCDPBox | None],
    ref_state: dict[str, int],
) -> BrowserCDPSnapshotNode | None:
    backend_node_id = ax_node.get("backendDOMNodeId")
    role = _ax_value(ax_node.get("role")) or "generic"
    name = _ax_value(ax_node.get("name"))
    value = _ax_value(ax_node.get("value"))
    properties = _ax_properties(ax_node)
    bounds = await _node_bounds(cdp, backend_node_id, box_cache)
    include_self = backend_node_id in backend_ids and (
        backend_node_id == root_backend_id
        or role != "generic"
        or name is not None
        or value is not None
    )
    ref = _next_ref(ref_state) if include_self else None

    child_nodes = []
    for child_id in ax_node.get("childIds", []):
        child_ax = ax_by_id.get(child_id)
        if child_ax is None:
            continue
        child_snapshot = await _build_snapshot_node(
            cdp=cdp,
            ax_by_id=ax_by_id,
            ax_node=child_ax,
            backend_ids=backend_ids,
            root_backend_id=root_backend_id,
            box_cache=box_cache,
            ref_state=ref_state,
        )
        if child_snapshot is not None:
            child_nodes.append(child_snapshot)

    if backend_node_id not in backend_ids:
        if len(child_nodes) == 1:
            return child_nodes[0]
        if child_nodes:
            return BrowserCDPSnapshotNode(
                ref=_next_ref(ref_state),
                role="generic",
                children=tuple(child_nodes),
            )
        return None

    should_include = include_self or bool(child_nodes)
    if not should_include:
        return None

    if ref is None:
        ref = _next_ref(ref_state)
    return BrowserCDPSnapshotNode(
        ref=ref,
        role=role,
        backend_node_id=backend_node_id,
        name=name,
        value=value,
        checked=_optional_bool(properties.get("checked")),
        disabled=_optional_bool(properties.get("disabled")),
        expanded=_optional_bool(properties.get("expanded")),
        bounds=bounds,
        children=tuple(child_nodes),
    )


def _ax_value(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ax_properties(ax_node: dict[str, Any]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for prop in ax_node.get("properties", []):
        name = prop.get("name")
        value = _ax_value(prop.get("value"))
        if name and value is not None:
            properties[name] = value
    return properties


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    return None


async def _node_bounds(
    cdp: Any,
    backend_node_id: int | None,
    cache: dict[int, BrowserCDPBox | None],
) -> BrowserCDPBox | None:
    if backend_node_id is None:
        return None
    if backend_node_id in cache:
        return cache[backend_node_id]
    try:
        payload = await cdp.send("DOM.getBoxModel", {"backendNodeId": backend_node_id})
        quad = payload["model"]["border"]
        xs = quad[0::2]
        ys = quad[1::2]
        box = BrowserCDPBox(
            x=min(xs),
            y=min(ys),
            width=max(xs) - min(xs),
            height=max(ys) - min(ys),
        )
        cache[backend_node_id] = box
        return box
    except Exception:
        cache[backend_node_id] = None
        return None


def _collect_backend_ids(node: dict[str, Any]) -> set[int]:
    backend_ids: set[int] = set()

    def visit(current: dict[str, Any]) -> None:
        backend_node_id = current.get("backendNodeId")
        if isinstance(backend_node_id, int):
            backend_ids.add(backend_node_id)
        for child in current.get("children", []):
            visit(child)
        for shadow_root in current.get("shadowRoots", []):
            visit(shadow_root)
        content_document = current.get("contentDocument")
        if isinstance(content_document, dict):
            visit(content_document)

    visit(node)
    return backend_ids


def _build_annotations(
    *,
    snapshot: BrowserCDPSnapshot,
    layout_metrics: dict[str, Any],
    full_page: bool,
    clip: dict[str, float] | None,
) -> tuple[BrowserCDPAnnotation, ...]:
    if snapshot.root is None:
        return ()

    visual_viewport = layout_metrics.get("cssVisualViewport", {})
    viewport = BrowserCDPBox(
        x=float(visual_viewport.get("pageX", 0.0)),
        y=float(visual_viewport.get("pageY", 0.0)),
        width=float(visual_viewport.get("clientWidth", 0.0)),
        height=float(visual_viewport.get("clientHeight", 0.0)),
    )

    if clip is not None:
        frame = BrowserCDPBox(
            x=float(clip["x"]),
            y=float(clip["y"]),
            width=float(clip["width"]),
            height=float(clip["height"]),
        )
    elif full_page:
        content_size = layout_metrics.get("cssContentSize", {})
        frame = BrowserCDPBox(
            x=0.0,
            y=0.0,
            width=float(content_size.get("width", viewport.width)),
            height=float(content_size.get("height", viewport.height)),
        )
    else:
        frame = viewport

    annotations: list[BrowserCDPAnnotation] = []
    for node in snapshot.refs.values():
        if node.role not in INTERACTIVE_ROLES or node.bounds is None:
            continue
        if not node.bounds.intersects(frame):
            continue
        annotations.append(
            BrowserCDPAnnotation(
                ref=node.ref,
                label=str(len(annotations) + 1),
                role=node.role,
                name=node.name,
                bounds=node.bounds.translated(dx=-frame.x, dy=-frame.y),
            )
        )

    return tuple(annotations)


def _next_ref(state: dict[str, int]) -> str:
    state["next_ref"] += 1
    return f"e{state['next_ref']}"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
