import asyncio
import shutil
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle
from dotenv import load_dotenv

load_dotenv()


async def main():
    output_dir = Path(__file__).resolve().parent / "screenshots"
    output_dir.mkdir(exist_ok=True)

    browser = Browser(
        cdp_url="http://localhost:3000"  # Your Browserless CDP URL
    )

    llm = ChatGoogle(model="gemini-flash-latest")
    agent = Agent(
        task="Go to YouTube.com and Press on a Video, Skip the Ads as Well",
        llm=llm,
        browser=browser,
        max_failures=1,
    )
    history = await agent.run()

    print(type(history))
    print(history.final_result())
    print(history.is_done())
    print(history.is_successful())
    print(history.last_action())
    print(history.model_actions())
    print(history.errors())
    print(history.usage)

    print("latest memory:", agent.state.last_model_output.memory)
    print("compacted memory:", agent.state.message_manager_state.compacted_memory)

    for item in agent.state.message_manager_state.agent_history_items:
        print(item.step_number, item.memory)

    print("saved screenshots:")
    for step_number, screenshot_path in enumerate(history.screenshot_paths(), 1):
        if not screenshot_path:
            continue

        source_path = Path(screenshot_path)
        destination_path = (
            output_dir / f"step_{step_number:02d}{source_path.suffix or '.png'}"
        )
        shutil.copy2(source_path, destination_path)
        print(step_number, destination_path)


if __name__ == "__main__":
    asyncio.run(main())
