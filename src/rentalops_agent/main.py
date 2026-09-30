from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from rentalops_agent.agent import Agent

app = FastAPI(title="RentalOps Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@lru_cache
def get_agent() -> Agent:
    return Agent()


class AgentRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


@app.post("/agent/execute")
async def execute(request: AgentRequest, agent: Annotated[Agent, Depends(get_agent)]):
    return StreamingResponse(
        agent.execute(request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
