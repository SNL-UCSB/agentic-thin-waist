import os
from pathlib import Path

from anthropic import Anthropic
from app.engine.executor import ToolRouter


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK for Steps 3–4."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self.api_key = (
            api_key
            or os.environ.get("CLAUDE_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY or ANTHROPIC_API_KEY must be set")
        self.client = Anthropic(api_key=self.api_key)
        self.model = model

    def _load_system_prompt(self) -> str:
        """Load the base system prompt and append knowledge files."""
        base_dir = Path(__file__).parent.parent
        prompt_path = base_dir / "prompts" / "system.md"
        knowledge_dir = base_dir / "knowledge"

        prompt = prompt_path.read_text()
        for knowledge_file in sorted(knowledge_dir.glob("*.md")):
            prompt += f"\n\n# {knowledge_file.stem}\n\n"
            prompt += knowledge_file.read_text()
        return prompt

    def send(self, user_message: str, system_prompt: str = "") -> str:
        """Send a single message to Claude and return the text response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # Step 3 keeps this simple: assume a single text block is returned
        return response.content[0].text

    def send_with_default_system(self, user_message: str) -> str:
        """Send a message using the default thin-waist system prompt."""
        system_prompt = self._load_system_prompt()
        return self.send(user_message=user_message, system_prompt=system_prompt)

    def send_with_tools(
        self, user_message: str, system_prompt: str, tools: list[dict]
    ) -> dict:
        """Send a message with OpenClaw tools enabled and return raw response blocks."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
        )
        text_blocks: list[str] = []
        tool_uses: list[dict] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_blocks.append(block.text)
            if getattr(block, "type", None) == "tool_use":
                tool_uses.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return {"text": "\n".join(text_blocks).strip(), "tool_uses": tool_uses}

    def execute_tool_loop(
        self, user_message: str, tools: list[dict], max_rounds: int = 5
    ) -> dict:
        """Run a minimal Anthropic tool-use loop until no tool call remains."""
        system_prompt = self._load_system_prompt()
        router = ToolRouter()
        history: list[dict] = [{"role": "user", "content": user_message}]
        final_text = ""

        for _ in range(max_rounds):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                tools=tools,
                messages=history,
            )
            tool_uses = []
            text_blocks = []
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    text_blocks.append(block.text)
                elif getattr(block, "type", None) == "tool_use":
                    tool_uses.append(block)
            final_text = "\n".join(text_blocks).strip()
            if not tool_uses:
                return {"text": final_text, "tool_results": []}

            tool_results = []
            tool_result_blocks = []
            for tool_use in tool_uses:
                result = router.handle_tool_call(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "tool_name": tool_use.name,
                        "input": tool_use.input,
                        "output": result,
                    }
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": str(result),
                    }
                )
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user", "content": tool_result_blocks})

        return {"text": final_text, "tool_results": tool_results}
