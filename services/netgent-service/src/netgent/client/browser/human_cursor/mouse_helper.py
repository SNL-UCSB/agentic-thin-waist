"""Inject a visible cursor element into the page for debugging."""

from __future__ import annotations

from playwright.async_api import Page as AsyncPage
from playwright.sync_api import Page as SyncPage

_MOUSE_HELPER_SCRIPT = """
() => {
    const box = document.createElement('p-mouse-pointer');
    const styleElement = document.createElement('style');
    styleElement.innerHTML = `
        p-mouse-pointer {
            pointer-events: none;
            position: absolute;
            top: 0;
            z-index: 10000;
            left: 0;
            width: 20px;
            height: 20px;
            background: rgba(0,0,0,.4);
            border: 1px solid white;
            border-radius: 10px;
            box-sizing: border-box;
            margin: -10px 0 0 -10px;
            padding: 0;
            transition: background .2s, border-radius .2s, border-color .2s;
        }
        p-mouse-pointer.button-1 {
            transition: none;
            background: rgba(0,0,0,0.9);
        }
        p-mouse-pointer.button-2 {
            transition: none;
            border-color: rgba(0,0,255,0.9);
        }
        p-mouse-pointer.button-3 {
            transition: none;
            border-radius: 4px;
        }
        p-mouse-pointer.button-4 {
            transition: none;
            border-color: rgba(255,0,0,0.9);
        }
        p-mouse-pointer.button-5 {
            transition: none;
            border-color: rgba(0,255,0,0.9);
        }
        p-mouse-pointer-hide {
            display: none;
        }
    `;
    document.head.appendChild(styleElement);
    document.body.appendChild(box);

    function updateButtons(buttons) {
        for (let i = 0; i < 5; i++) {
            box.classList.toggle('button-' + i, Boolean(buttons & (1 << i)));
        }
    }

    document.addEventListener('mousemove', e => {
        box.style.left = e.pageX + 'px';
        box.style.top = e.pageY + 'px';
        box.classList.remove('p-mouse-pointer-hide');
        updateButtons(e.buttons);
    }, true);

    document.addEventListener('mousedown', e => {
        updateButtons(e.buttons);
        box.classList.add('button-' + e.which);
        box.classList.remove('p-mouse-pointer-hide');
    }, true);

    document.addEventListener('mouseup', e => {
        updateButtons(e.buttons);
        box.classList.remove('button-' + e.which);
        box.classList.remove('p-mouse-pointer-hide');
    }, true);

    document.addEventListener('mouseleave', e => {
        updateButtons(e.buttons);
        box.classList.add('p-mouse-pointer-hide');
    }, true);

    document.addEventListener('mouseenter', e => {
        updateButtons(e.buttons);
        box.classList.remove('p-mouse-pointer-hide');
    }, true);
}
"""


async def install_mouse_helper_async(page: AsyncPage) -> None:
    """Inject a visible cursor overlay into *page* (async Playwright)."""
    await page.add_init_script(_MOUSE_HELPER_SCRIPT)
    await page.evaluate(_MOUSE_HELPER_SCRIPT)


def install_mouse_helper(page: SyncPage) -> None:
    """Inject a visible cursor overlay into *page* (sync Playwright)."""
    page.add_init_script(_MOUSE_HELPER_SCRIPT)
    page.evaluate(_MOUSE_HELPER_SCRIPT)
