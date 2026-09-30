import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from rentalops_agent.tools import get_weather


def build_graph() -> StateGraph:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    model = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        reasoning_effort="none",
    ).bind_tools([get_weather])

    async def call_model(state: MessagesState):
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode([get_weather]))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "model")
    return builder
