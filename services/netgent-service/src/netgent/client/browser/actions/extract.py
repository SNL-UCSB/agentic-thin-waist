from __future__ import annotations

from typing import TYPE_CHECKING, Any

from netgent.client.browser.exception import BrowserSessionError
from netgent.client.browser.models import (
    BrowserDropdownOption,
    BrowserFindTextResult,
)
from netgent.client.browser.snapshot import BrowserCDPSnapshot

from netgent.client.browser.actions import refs as ref_actions

if TYPE_CHECKING:
    from netgent.client.browser.client import BrowserSession


async def find_text(
    session: BrowserSession,
    text: str,
    *,
    exact: bool = False,
) -> BrowserFindTextResult:
    locator = session.page.get_by_text(text, exact=exact)
    count = await locator.count()
    visible = False
    matches: list[str] = []

    for index in range(min(count, 5)):
        node = locator.nth(index)
        try:
            visible = visible or await node.is_visible()
            matches.append(await node.inner_text())
        except Exception:
            continue

    return BrowserFindTextResult(
        query=text,
        count=count,
        visible=visible,
        matches=tuple(matches),
    )


async def send_keys(
    session: BrowserSession,
    keys: str | tuple[str, ...] | list[str],
) -> None:
    if isinstance(keys, str):
        await session.page.keyboard.press(keys)
        return
    for key in keys:
        await session.page.keyboard.press(key)


async def evaluate(
    session: BrowserSession, expression: str, arg: Any | None = None
) -> Any:
    return await session.page.evaluate(expression, arg)


async def dropdown_options(
    session: BrowserSession,
    *,
    ref: str | None = None,
    selector: str | None = None,
    snapshot: BrowserCDPSnapshot | None = None,
) -> tuple[BrowserDropdownOption, ...]:
    if ref is not None:
        await ref_actions.click_ref(session, ref, snapshot=snapshot)
        payload = await session.page.evaluate(_ACTIVE_DROPDOWN_OPTIONS_SCRIPT)
    elif selector is not None:
        payload = await session.page.locator(selector).first.evaluate(
            _ELEMENT_DROPDOWN_OPTIONS_SCRIPT
        )
    else:
        raise BrowserSessionError("dropdown_options requires either ref or selector")

    return tuple(BrowserDropdownOption.model_validate(item) for item in payload)


async def select_dropdown(
    session: BrowserSession,
    *,
    ref: str | None = None,
    selector: str | None = None,
    label: str | None = None,
    value: str | None = None,
    index: int | None = None,
    snapshot: BrowserCDPSnapshot | None = None,
) -> Any:
    if selector is not None:
        locator = session.page.locator(selector).first
        kwargs = {}
        if label is not None:
            kwargs["label"] = label
        if value is not None:
            kwargs["value"] = value
        if index is not None:
            kwargs["index"] = index
        return await locator.select_option(**kwargs)

    if ref is None:
        raise BrowserSessionError("select_dropdown requires either ref or selector")

    await ref_actions.click_ref(session, ref, snapshot=snapshot)
    selected = await session.page.evaluate(
        _ACTIVE_DROPDOWN_SELECT_SCRIPT,
        {"label": label, "value": value, "index": index},
    )
    if selected is None:
        raise BrowserSessionError(f"Unable to select dropdown option for ref {ref!r}")
    return selected


async def extract(
    session: BrowserSession,
    *,
    selector: str = "body",
    mode: str = "text",
    timeout_ms: float | None = None,
) -> Any:
    if mode == "snapshot":
        captured = await session.snapshot(selector=selector, timeout_ms=timeout_ms)
        return captured.model_dump(mode="json")
    if mode == "markdown":
        captured = await session.snapshot(selector=selector, timeout_ms=timeout_ms)
        return captured.markdown

    locator = session.page.locator(selector).first
    await locator.wait_for(state="attached", timeout=timeout_ms)

    if mode == "text":
        return await locator.inner_text()
    if mode == "html":
        return await locator.evaluate("(element) => element.outerHTML")

    raise BrowserSessionError(f"Unsupported extract mode {mode!r}")


_ELEMENT_DROPDOWN_OPTIONS_SCRIPT = """
(element) => {
  if (!element) return [];
  if (element.tagName === 'SELECT') {
    return Array.from(element.options).map((option) => ({
      label: option.label || option.textContent || '',
      value: option.value || '',
      selected: option.selected,
      disabled: option.disabled,
    }));
  }

  const ownerId = element.getAttribute('aria-controls') || element.getAttribute('aria-owns');
  const owner = ownerId ? document.getElementById(ownerId) : null;
  const optionsRoot = owner || document;
  return Array.from(optionsRoot.querySelectorAll('[role="option"]')).map((option) => ({
    label: (option.innerText || option.textContent || '').trim(),
    value: option.getAttribute('data-value') || option.getAttribute('value') || '',
    selected: option.getAttribute('aria-selected') === 'true',
    disabled: option.getAttribute('aria-disabled') === 'true',
  }));
}
"""


_ACTIVE_DROPDOWN_OPTIONS_SCRIPT = """
() => {
  const element = document.activeElement;
  if (!element) return [];
  if (element.tagName === 'SELECT') {
    return Array.from(element.options).map((option) => ({
      label: option.label || option.textContent || '',
      value: option.value || '',
      selected: option.selected,
      disabled: option.disabled,
    }));
  }

  const ownerId = element.getAttribute('aria-controls') || element.getAttribute('aria-owns');
  const owner = ownerId ? document.getElementById(ownerId) : null;
  const optionsRoot = owner || document;
  return Array.from(optionsRoot.querySelectorAll('[role="option"]')).map((option) => ({
    label: (option.innerText || option.textContent || '').trim(),
    value: option.getAttribute('data-value') || option.getAttribute('value') || '',
    selected: option.getAttribute('aria-selected') === 'true',
    disabled: option.getAttribute('aria-disabled') === 'true',
  }));
}
"""


_ACTIVE_DROPDOWN_SELECT_SCRIPT = """
(target) => {
  const element = document.activeElement;
  if (!element) return null;

  if (element.tagName === 'SELECT') {
    const options = Array.from(element.options);
    const option = options.find((candidate, idx) => (
      (target.index !== null && idx === target.index) ||
      (target.value !== null && candidate.value === target.value) ||
      (target.label !== null && (candidate.label || candidate.textContent || '').trim() === target.label)
    ));
    if (!option) return null;
    element.value = option.value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return option.value;
  }

  const ownerId = element.getAttribute('aria-controls') || element.getAttribute('aria-owns');
  const owner = ownerId ? document.getElementById(ownerId) : null;
  const optionsRoot = owner || document;
  const options = Array.from(optionsRoot.querySelectorAll('[role="option"]'));
  const option = options.find((candidate, idx) => (
    (target.index !== null && idx === target.index) ||
    (target.value !== null && (
      candidate.getAttribute('data-value') === target.value ||
      candidate.getAttribute('value') === target.value
    )) ||
    (target.label !== null && (candidate.innerText || candidate.textContent || '').trim() === target.label)
  ));
  if (!option) return null;
  option.click();
  return (
    option.getAttribute('data-value') ||
    option.getAttribute('value') ||
    (option.innerText || option.textContent || '').trim()
  );
}
"""
