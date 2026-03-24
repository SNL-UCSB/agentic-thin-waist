from __future__ import annotations

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from netgent.agent.schema import NetGentState, call_llm

load_dotenv()


def build_graph():
    graph_builder = StateGraph(NetGentState)
    graph_builder.add_node("call_llm", call_llm)
    graph_builder.add_edge(START, "call_llm")
    graph_builder.add_edge("call_llm", END)
    return graph_builder.compile()


graph = build_graph()
