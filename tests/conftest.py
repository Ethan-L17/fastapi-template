"""共享测试夹具。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """创建一个不连接外部服务的 FastAPI 测试客户端。

    lifespan 中的 MCP 连接和 PostgreSQL checkpointer 被 mock 掉。
    """
    with patch("main.MCPClientManager") as MockMCP, \
         patch("main.CheckpointerManager") as MockCP:
        # MCP manager mock
        mock_mcp = AsyncMock()
        mock_mcp.connections = {}
        MockMCP.return_value = mock_mcp

        # Checkpointer mock — 默认禁用
        mock_cp = AsyncMock()
        mock_cp.checkpointer = None
        MockCP.return_value = mock_cp

        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
