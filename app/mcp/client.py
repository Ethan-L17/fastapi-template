"""MCP Client Manager – maintains connections to multiple MCP servers."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from app.mcp.config import MCPConfigProvider, MCPServerConfig, TransportType

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    """A live connection to a single MCP server."""

    name: str
    config: MCPServerConfig
    session: ClientSession
    _stack: AsyncExitStack = field(repr=False)


class MCPClientManager:
    """Manage the lifecycle of multiple MCP client connections.

    Usage (with FastAPI lifespan):
        manager = MCPClientManager(provider)
        await manager.start()   # connect to all configured servers
        ...
        await manager.stop()    # graceful shutdown
    """

    def __init__(self, provider: MCPConfigProvider) -> None:
        self._provider = provider
        self._connections: dict[str, MCPConnection] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        configs = await self._provider.load_servers()
        results = await asyncio.gather(
            *(self._connect(name, cfg) for name, cfg in configs.items()),
            return_exceptions=True,
        )
        for name, result in zip(configs, results):
            if isinstance(result, Exception):
                logger.error("Failed to connect MCP server '%s': %s", name, result)

    async def stop(self) -> None:
        async with self._lock:
            for name in list(self._connections):
                await self._disconnect(name)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _connect(self, name: str, config: MCPServerConfig) -> None:
        async with self._lock:
            if name in self._connections:
                logger.warning("MCP server '%s' already connected, skipping", name)
                return

            stack = AsyncExitStack()
            try:
                if config.transport == TransportType.STDIO:
                    session = await self._connect_stdio(stack, config)
                else:
                    session = await self._connect_sse(stack, config)

                self._connections[name] = MCPConnection(
                    name=name,
                    config=config,
                    session=session,
                    _stack=stack,
                )
                logger.info("Connected to MCP server '%s' via %s", name, config.transport.value)
            except Exception:
                await stack.aclose()
                raise

    async def _connect_stdio(
        self, stack: AsyncExitStack, config: MCPServerConfig
    ) -> ClientSession:
        params = StdioServerParameters(
            command=config.command,  # type: ignore[arg-type]
            args=config.args,
            env=config.env,
        )
        transport = await stack.enter_async_context(stdio_client(params))
        read_stream, write_stream = transport
        session: ClientSession = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return session

    async def _connect_sse(
        self, stack: AsyncExitStack, config: MCPServerConfig
    ) -> ClientSession:
        transport = await stack.enter_async_context(
            sse_client(
                url=config.url,  # type: ignore[arg-type]
                headers=config.headers if config.headers else None,
                timeout=config.timeout,
            )
        )
        read_stream, write_stream = transport
        session: ClientSession = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return session

    async def _disconnect(self, name: str) -> None:
        conn = self._connections.pop(name, None)
        if conn is None:
            return
        try:
            await conn._stack.aclose()
            logger.info("Disconnected MCP server '%s'", name)
        except Exception as exc:
            logger.error("Error disconnecting MCP server '%s': %s", name, exc)

    # ------------------------------------------------------------------
    # Runtime operations (hot-reload a single server)
    # ------------------------------------------------------------------

    async def reconnect(self, name: str) -> None:
        """Disconnect then reconnect a specific server by re-loading config."""
        async with self._lock:
            await self._disconnect(name)
        configs = await self._provider.load_servers()
        if name not in configs:
            raise KeyError(f"Server '{name}' not found in config")
        await self._connect(name, configs[name])

    async def reload_all(self) -> None:
        """Re-read config and reconcile connections (add new, remove stale)."""
        configs = await self._provider.load_servers()
        async with self._lock:
            current = set(self._connections)
            desired = set(configs)
            for stale in current - desired:
                await self._disconnect(stale)
        for new_name in desired - set(self._connections):
            await self._connect(new_name, configs[new_name])

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_connection(self, name: str) -> MCPConnection:
        conn = self._connections.get(name)
        if conn is None:
            raise KeyError(f"MCP server '{name}' is not connected")
        return conn

    @property
    def connections(self) -> dict[str, MCPConnection]:
        return dict(self._connections)

    async def list_server_tools(self, name: str) -> list[dict[str, Any]]:
        conn = self.get_connection(name)
        resp = await conn.session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
            }
            for t in resp.tools
        ]

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        conn = self.get_connection(server_name)
        result = await conn.session.call_tool(tool_name, arguments=arguments or {})
        return result

    async def list_server_resources(self, name: str) -> list[dict[str, Any]]:
        conn = self.get_connection(name)
        resp = await conn.session.list_resources()
        return [
            {"uri": str(r.uri), "name": r.name, "mimeType": r.mimeType}
            for r in resp.resources
        ]

    async def read_resource(self, server_name: str, uri: str) -> Any:
        conn = self.get_connection(server_name)
        result = await conn.session.read_resource(uri)
        return result
