from __future__ import annotations

import asyncio
from typing import Any


class NetGentEngine:
    def __init__(self):
        print("NetGentEngine initialized")

    async def execute(
        self,
        workflow: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> None:
        if workflow is not None:
            print(f"Loaded workflow with {len(workflow)} top-level fields")
        print(f"Start Workflow for {timeout} Seconds")
        await asyncio.sleep(timeout)
        print("Workflow completed")
