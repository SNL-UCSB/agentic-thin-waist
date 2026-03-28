import asyncio
import os
from datetime import datetime
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle, Controller
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, MessagesState
from langgraph.graph.state import StateGraph
from langgraph.runtime import Runtime
from playwright.async_api import Playwright, async_playwright
from pydantic import BaseModel, ConfigDict

from agent.subagents.browser.script_generator import save_history_and_script

model = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview")
browser_model = ChatGoogle(model="gemini-3.1-flash-lite-preview")
DEFAULT_ARTIFACTS_DIR = Path(
    os.getenv("NETGENT_BROWSER_ARTIFACTS_DIR", "artifacts/browser")
)
DEFAULT_MAX_STEPS = int(os.getenv("BROWSER_USE_MAX_STEPS", "30"))
DEFAULT_HEADLESS = os.getenv("BROWSER_USE_HEADLESS", "false").lower() == "true"
EXCLUDED_BROWSER_USE_ACTIONS = [
    "search_google",
    "extract_structured_data",
    "read_sheet_contents",
    "read_cell_contents",
    "update_cell_contents",
    "clear_cell_contents",
    "select_cell_or_range",
    "fallback_input_into_single_selected_cell",
    "upload_file",
]


class BrowserState(MessagesState):
    task: str
    final_result: str | None = None
    history_path: str | None = None
    script_path: str | None = None
    manifest_path: str | None = None
    script_warnings: list[str] = []


class BrowserContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    playwright: Playwright


async def execute_task(state: BrowserState, runtime: Runtime[BrowserContext]):
    browser = await runtime.context.playwright.chromium.launch(
        headless=DEFAULT_HEADLESS
    )
    try:
        browser_context = await browser.new_context()
        page = await browser_context.new_page()
        controller = Controller(exclude_actions=EXCLUDED_BROWSER_USE_ACTIONS)
        browser_agent = Agent(
            browser=Browser(
                browser=browser,
                browser_context=browser_context,
                page=page,
                playwright=runtime.context.playwright,
            ),
            controller=controller,
            llm=browser_model,
            task=state["task"],
            headless=DEFAULT_HEADLESS,
        )
        history = await browser_agent.run(max_steps=DEFAULT_MAX_STEPS)

        run_dir = DEFAULT_ARTIFACTS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
        artifacts = save_history_and_script(
            task=state["task"],
            history=history,
            output_dir=run_dir,
        )

        return {
            "final_result": history.final_result(),
            **artifacts,
        }
    finally:
        await browser.close()


def create_agent():
    graph = StateGraph(state_schema=BrowserState, context_schema=BrowserContext)
    graph.add_node("execute_task", execute_task)
    graph.add_edge(START, "execute_task")
    graph.add_edge("execute_task", END)
    return graph.compile()


async def main():
    playwright = await async_playwright().start()
    try:
        browser_agent = create_agent()
        response = await browser_agent.ainvoke(
            {
                "task": os.getenv(
                    "BROWSER_USE_TASK",
                    "1. Go to YouTube, 2. Search for A Active Content Creator, 3. Go to the First Stream 4. Watch the Video for 10 Seconds. 5. You must skip any ads on the screen. 6. Skip some parts of the Video",
                )
            },
            context={"playwright": playwright},
        )
        print(f"Result: {response.get('final_result')}")
        print(f"History: {response.get('history_path')}")
        print(f"Script: {response.get('script_path')}")
        if response.get("script_warnings"):
            print("Warnings:")
            for warning in response["script_warnings"]:
                print(f"- {warning}")
        return response
    finally:
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
