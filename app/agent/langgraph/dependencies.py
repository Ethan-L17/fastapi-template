"""FastAPI dependency injection for the LangGraph checkpointer."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.agent.langgraph.checkpointer import CheckpointerManager


async def get_checkpointer(request: Request) -> CheckpointerManager | None:
    mgr: CheckpointerManager | None = getattr(request.app.state, "checkpointer", None)
    return mgr


Checkpointer = Annotated[CheckpointerManager | None, Depends(get_checkpointer)]
