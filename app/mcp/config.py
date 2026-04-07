"""MCP server configuration models and providers.

Supports loading MCP server configs from JSON file, with an abstract
base class to allow future database-backed providers.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


class MCPServerConfig(BaseModel):
    """Single MCP server connection configuration."""

    transport: TransportType
    # stdio fields
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    # sse fields
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    # common
    enabled: bool = True
    timeout: float = 30.0

    def model_post_init(self, __context: Any) -> None:
        if self.transport == TransportType.STDIO and not self.command:
            raise ValueError("stdio transport requires 'command'")
        if self.transport == TransportType.SSE and not self.url:
            raise ValueError("sse transport requires 'url'")


class MCPServersFile(BaseModel):
    """Top-level schema for the JSON config file."""

    mcpServers: dict[str, MCPServerConfig] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract config provider – swap implementations for file / DB / remote
# ---------------------------------------------------------------------------


class MCPConfigProvider(ABC):
    """Base class for MCP server config providers."""

    @abstractmethod
    async def load_servers(self) -> dict[str, MCPServerConfig]:
        """Return a mapping of server_name -> config."""
        ...


class FileConfigProvider(MCPConfigProvider):
    """Load MCP server configs from a local JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def load_servers(self) -> dict[str, MCPServerConfig]:
        if not self.path.exists():
            logger.warning("MCP config file not found: %s", self.path)
            return {}
        text = self.path.read_text(encoding="utf-8")
        data = json.loads(text)
        parsed = MCPServersFile.model_validate(data)
        servers = {
            name: cfg
            for name, cfg in parsed.mcpServers.items()
            if cfg.enabled
        }
        logger.info("Loaded %d MCP server(s) from %s", len(servers), self.path)
        return servers


class DatabaseConfigProvider(MCPConfigProvider):
    """Placeholder: load MCP server configs from a database.

    Implement this class when you want to manage MCP servers dynamically
    via a database (e.g. per-user or per-tenant configs).

    Expected usage:
        provider = DatabaseConfigProvider(db_session)
        servers = await provider.load_servers()
    """

    def __init__(self, db_session: Any = None) -> None:
        self.db_session = db_session

    async def load_servers(self) -> dict[str, MCPServerConfig]:
        # TODO: query your ORM / raw SQL here and return MCPServerConfig dicts
        # Example:
        #   rows = await self.db_session.execute(select(MCPServerModel).where(...))
        #   return {row.name: MCPServerConfig(**row.config) for row in rows}
        raise NotImplementedError(
            "DatabaseConfigProvider is a placeholder – implement your DB query logic"
        )
