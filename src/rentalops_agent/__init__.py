"""Agente RentalOps com eventos nativos do LangGraph."""


def main() -> None:
    """Inicia a API pelo comando `uv run rentalops-agent`."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="API do RentalOps Agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("rentalops_agent.main:app", host=args.host, port=args.port, reload=args.reload)
