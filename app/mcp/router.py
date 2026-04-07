"""API routes for interacting with connected MCP servers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp.dependencies import MCPManager

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: dict[str, Any] | None = None


class ResourceReadRequest(BaseModel):
    server_name: str
    uri: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/servers")
async def list_servers(mgr: MCPManager):
    """List all connected MCP servers and their transport type."""
    return {
        name: {
            "transport": conn.config.transport.value,
            "enabled": conn.config.enabled,
        }
        for name, conn in mgr.connections.items()
    }


@router.get("/servers/{server_name}/tools")
async def list_tools(server_name: str, mgr: MCPManager):
    """List tools exposed by a specific MCP server."""
    try:
        tools = await mgr.list_server_tools(server_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not connected")
    return {"server": server_name, "tools": tools}


@router.post("/tools/call")
async def call_tool(body: ToolCallRequest, mgr: MCPManager):
    """Call a tool on a connected MCP server."""
    try:
        result = await mgr.call_tool(body.server_name, body.tool_name, body.arguments)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Server '{body.server_name}' not connected"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    content_list = []
    for block in result.content:
        item: dict[str, Any] = {"type": block.type}
        if hasattr(block, "text"):
            item["text"] = block.text
        if hasattr(block, "data"):
            item["data"] = block.data
        if hasattr(block, "mimeType"):
            item["mimeType"] = block.mimeType
        content_list.append(item)

    return {"server": body.server_name, "tool": body.tool_name, "content": content_list}


@router.get("/servers/{server_name}/resources")
async def list_resources(server_name: str, mgr: MCPManager):
    """List resources exposed by a specific MCP server."""
    try:
        resources = await mgr.list_server_resources(server_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not connected")
    return {"server": server_name, "resources": resources}


@router.post("/resources/read")
async def read_resource(body: ResourceReadRequest, mgr: MCPManager):
    """Read a resource from a connected MCP server."""
    try:
        result = await mgr.read_resource(body.server_name, body.uri)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Server '{body.server_name}' not connected"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    content_list = []
    for block in result.contents:
        item: dict[str, Any] = {"uri": str(block.uri)}
        if hasattr(block, "text"):
            item["text"] = block.text
        if hasattr(block, "mimeType"):
            item["mimeType"] = block.mimeType
        content_list.append(item)

    return {"server": body.server_name, "uri": body.uri, "contents": content_list}


@router.post("/servers/reload")
async def reload_servers(mgr: MCPManager):
    """Reload MCP server configs and reconcile connections."""
    await mgr.reload_all()
    return {"status": "ok", "servers": list(mgr.connections.keys())}


@router.post("/servers/{server_name}/reconnect")
async def reconnect_server(server_name: str, mgr: MCPManager):
    """Reconnect a specific MCP server."""
    try:
        await mgr.reconnect(server_name)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Server '{server_name}' not found in config"
        )
    return {"status": "ok", "server": server_name}
