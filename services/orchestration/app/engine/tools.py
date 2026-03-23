"""OpenClaw tool declarations and runtime loader (Step 9)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_HEADER_RE = re.compile(r"^##\s+([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)\s*$")
_ARG_RE = re.compile(
    r"^-\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+\(([^)]+)\):\s*(.+)$"
)


def _infer_json_type(type_text: str) -> str:
    t = type_text.lower()
    if "float" in t or "number" in t:
        return "number"
    if "int" in t:
        return "integer"
    if "bool" in t:
        return "boolean"
    if "array" in t or "list" in t:
        return "array"
    if "object" in t or "dict" in t:
        return "object"
    return "string"


def _tools_md_path() -> Path:
    return Path(__file__).resolve().parents[2] / "TOOLS.md"


def load_tools() -> list[dict[str, Any]]:
    """Load tool declarations from TOOLS.md into Anthropic/OpenClaw schema."""
    path = _tools_md_path()
    text = path.read_text()
    lines = text.splitlines()

    tools: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw in lines:
        line = raw.rstrip()
        header = _HEADER_RE.match(line)
        if header:
            if current is not None:
                tools.append(current)
            current = {
                "name": header.group(1),
                "description": "",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
            continue

        if current is None:
            continue

        arg_match = _ARG_RE.match(line)
        if arg_match:
            arg_name, arg_type, arg_desc = arg_match.groups()
            optional = "optional" in arg_type.lower()
            json_type = _infer_json_type(arg_type)
            current["input_schema"]["properties"][arg_name] = {
                "type": json_type,
                "description": arg_desc.strip(),
            }
            if not optional:
                current["input_schema"]["required"].append(arg_name)
            continue

        if line.startswith("Returns:"):
            continue

        if line and not line.startswith("#"):
            if current["description"]:
                current["description"] += " "
            current["description"] += line.strip()

    if current is not None:
        tools.append(current)

    for tool in tools:
        if not tool["input_schema"]["required"]:
            tool["input_schema"].pop("required", None)

    return tools

