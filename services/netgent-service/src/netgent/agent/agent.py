from __future__ import annotations

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph, MessagesState
from langchain_google_genai import ChatGoogleGenerativeAI
from netgent.client.browser import BrowserSession, BrowserCDPSnapshot


load_dotenv()


class NetGentState(MessagesState):
    browser: BrowserSession
    snapshot: BrowserCDPSnapshot


model = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview")


async def annotate(state: NetGentState) -> NetGentState:
    snapshot = await state.browser.snapshot()
    return {"snapshot": snapshot}


def click(state: NetGentState) -> NetGentState:
    return state


def input(state: NetGentState) -> NetGentState:
    return state


def scroll(state: NetGentState) -> NetGentState:
    return state


def done(state: NetGentState) -> NetGentState:
    return state


def build_graph():
    graph = StateGraph(NetGentState)
    graph.add_node("annotate", annotate)
    graph.add_node("decide", decide)
    graph.add_node("click", click)
    graph.add_node("input", input)
    graph.add_node("scroll", scroll)
    graph.add_node("done", done)
    graph.add_edge(START, "annotate")
    graph.add_edge("annotate", "decide")
    graph.add_edge("decide", "click")
    graph.add_edge("decide", "input")
    graph.add_edge("decide", "scroll")
    graph.add_edge("decide", "done")
    graph.add_edge("click", "annotate")
    graph.add_edge("input", "annotate")
    graph.add_edge("scroll", "annotate")
    graph.add_edge("done", END)
    return graph.compile()


graph = build_graph()
