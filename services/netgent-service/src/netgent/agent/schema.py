from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from netgent.client.browser import BrowserCDPSnapshot


class NetGentState(MessagesState, total=False):
    snapshot: BrowserCDPSnapshot


class NetGentContext(TypedDict, total=False):
    browser: Any
    thread_id: str


class NetGentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClickTool(NetGentToolCall):
    ref: str = Field(min_length=1)
    button: Literal["left", "middle", "right"] = "left"
    click_count: int = Field(default=1, ge=1)


class InputTool(NetGentToolCall):
    text: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    clear: bool = True
    delay_ms: float = Field(default=50, ge=0)
    press_enter: bool = False


class ScrollTool(NetGentToolCall):
    ref: str = Field(min_length=1)
    align: Literal["top", "center", "bottom"] = "center"


class DoneTool(NetGentToolCall):
    answer: str | None = None
