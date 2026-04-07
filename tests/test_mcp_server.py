"""Minimal MCP server for testing both stdio and SSE transports.

Usage:
    # SSE mode (default, on port 3001):
    uv run python tests/test_mcp_server.py

    # stdio mode:
    uv run python tests/test_mcp_server.py --stdio
"""

import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-server", host="127.0.0.1", port=3001)


@mcp.tool()
def echo(message: str) -> str:
    """Echo back the input message."""
    return f"echo: {message}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse")
