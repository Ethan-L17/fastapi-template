"""FastAPI dependency injection for MCP client manager."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.mcp.client import MCPClientManager


async def get_mcp_manager(request: Request) -> MCPClientManager:
    mgr: MCPClientManager | None = getattr(request.app.state, "mcp_manager", None)
    if mgr is None:
        raise HTTPException(status_code=503, detail="MCP client manager not initialized")
    return mgr


MCPManager = Annotated[MCPClientManager, Depends(get_mcp_manager)]
