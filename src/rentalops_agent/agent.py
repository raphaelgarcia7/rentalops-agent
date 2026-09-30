import json
from collections.abc import AsyncIterator

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import HumanMessage

from rentalops_agent.graph import build_graph


class Agent:
    def __init__(self) -> None:
        self.graph = build_graph().compile()

    async def execute(self, message: str) -> AsyncIterator[str]:
        async for event in self.graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            include_types=["chat_model", "tool"],
        ):
            payload = json.dumps(jsonable_encoder(event), ensure_ascii=False)
            yield f"event: {event['event']}\ndata: {payload}\n\n"
