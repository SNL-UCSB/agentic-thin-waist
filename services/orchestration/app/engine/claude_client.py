import os
from pathlib import Path

from anthropic import Anthropic


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
