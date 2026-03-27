#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib
import os

from browser_use import Browser as RealBrowser

CDP_URL = os.getenv("BROWSER_USE_CDP_URL", "ws://browserless:3000/")


def main() -> None:
    module = importlib.import_module("netgent.browser-use.main")

    class Browser(RealBrowser):
        def __init__(self, *args, **kwargs):
            kwargs["cdp_url"] = CDP_URL
            super().__init__(*args, **kwargs)

    module.Browser = Browser
    asyncio.run(module.main())


if __name__ == "__main__":
    main()
