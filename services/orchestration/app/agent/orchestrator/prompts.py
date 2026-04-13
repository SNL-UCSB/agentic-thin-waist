"""Prompt templates for the Orchestrator Agent."""

from pathlib import Path

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)


def _load_system_prompt_text() -> str:
    """Load system.md and append all knowledge files."""
    base_dir = Path(__file__).resolve().parents[2]
    prompt_path = base_dir / "prompts" / "system.md"
    knowledge_dir = base_dir / "knowledge"

    text = prompt_path.read_text()
    for knowledge_file in sorted(knowledge_dir.glob("*.md")):
        text += f"\n\n# {knowledge_file.stem}\n\n"
        text += knowledge_file.read_text()
    return text


def _load_examples_text() -> str:
    """Load few-shot examples from examples.md."""
    base_dir = Path(__file__).resolve().parents[2]
    examples_path = base_dir / "prompts" / "examples.md"
    if examples_path.exists():
        return examples_path.read_text()
    return ""


SYSTEM_PROMPT_TEXT = _load_system_prompt_text()
EXAMPLES_TEXT = _load_examples_text()

SYSTEM_TEMPLATE = SystemMessagePromptTemplate.from_template(
    SYSTEM_PROMPT_TEXT,
    template_format="mustache",
)

PARSE_INTENT_TEMPLATE = HumanMessagePromptTemplate.from_template(
    """{{{examples_block}}}Extract experiment parameters from the following research intent.

You already know the valid applications, parameter ranges, defaults,
and constraints from your Thin Waist system prompt and knowledge files.
Use that knowledge to interpret the intent, but DO NOT invent parameters
that the user has not implied. Prefer asking for clarification when needed.

Intent: {{{intent}}}""",
    template_format="mustache",
)

PARSE_INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [SYSTEM_TEMPLATE, PARSE_INTENT_TEMPLATE]
)


def build_examples_block() -> str:
    """Return the few-shot preamble if examples are available, else empty string."""
    if not EXAMPLES_TEXT:
        return ""
    return (
        "Here are a few prior intents and their extracted parameters "
        "for you to use as reference examples only. Do not echo them "
        "in your response; just use them to calibrate your behaviour.\n\n"
        + EXAMPLES_TEXT
        + "\n\nNow, independently of those examples, "
        "extract parameters for the NEW intent below.\n\n"
    )
