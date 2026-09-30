import asyncio

from langchain_core.tools import tool


@tool
async def get_weather(city: str) -> dict:
    """Retorna o clima de demonstração de uma cidade, sem consultar serviços externos."""
    await asyncio.sleep(2)
    return {"city": city, "temp_c": 22, "condition": "parcialmente nublado"}
