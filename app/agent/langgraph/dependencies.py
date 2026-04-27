"""FastAPI dependency injection for the LangGraph checkpointer."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.agent.langgraph.checkpointer import CheckpointerManager


async def get_checkpointer(request: Request) -> CheckpointerManager:
    mgr: CheckpointerManager | None = getattr(request.app.state, "checkpointer", None)
    if mgr is None:
        raise HTTPException(
            status_code=503, detail="Checkpointer manager not initialized"
        )
    return mgr


Checkpointer = Annotated[CheckpointerManager, Depends(get_checkpointer)]
