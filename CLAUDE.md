# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Install with dev dependencies (pytest, httpx, ruff)
uv sync --group dev

# Start dev server (recommended — handles Windows event-loop policy)
uv run python run.py

# Or start with uvicorn directly
uv run uvicorn main:app --reload

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_mcp_server.py -k <test_name>

# Lint
uv run ruff check .

# Start the test MCP server (SSE mode, port 3001)
uv run python tests/test_mcp_server.py

# Start the test MCP server (stdio mode)
uv run python tests/test_mcp_server.py --stdio
```

Python version: 3.10 (as specified in `.python-version`).

## Architecture

### Application Lifecycle (`main.py`)

The app is created with a `lifespan` async context manager in `main.py` that:

1. **Startup**: Creates a `FileConfigProvider` → `MCPClientManager` and connects to all enabled MCP servers. Then creates a `CheckpointerManager` (PostgreSQL connection pool) and runs DB schema setup.
2. **Shutdown**: Closes the checkpointer pool, then disconnects all MCP servers.

Both managers are stored on `app.state` for the dependency injection layer to access.

### MCP Client System (`app/mcp/`)

This app acts as an **MCP Client**, connecting to external MCP servers.

- **`config.py`** — `MCPServerConfig` Pydantic model (supports `stdio` and `sse` transports). `MCPConfigProvider` is an abstract base class with `FileConfigProvider` (reads `mcp_servers.json`) and a `DatabaseConfigProvider` placeholder for future DB-backed config. Use the `MCP_CONFIG_PATH` env var to change the config file path.
- **`client.py`** — `MCPClientManager` handles connection lifecycle (connect/disconnect/reconnect/reload_all). Each connection is wrapped in an `AsyncExitStack` for clean teardown.
- **`router.py`** — REST API at `/api/mcp/...` for listing servers, tools, resources, and calling tools/reading resources. Also provides `/servers/reload` (hot-reload from config) and `/servers/{name}/reconnect`.
- **`dependencies.py`** — `MCPManager` type annotation for FastAPI dependency injection, pulling `mcp_manager` from `app.state`.

### LangGraph Agent System (`app/agent/`)

- **`checkpointer.py`** — `CheckpointerManager` wraps `psycopg`'s `AsyncConnectionPool` and `AsyncPostgresSaver`. Each workflow is isolated via `checkpoint_ns`. Call `build_config(workflow, thread_id)` to get the LangGraph config dict.
- **`react.py`** — Builds a ReAct agent `StateGraph` (agent → conditional → tools → agent). The graph nodes are **mock placeholders** — replace `_call_model` with a real LLM call and `_call_tools` with actual tool execution. `WORKFLOW_NAME = "react_agent"` is the checkpoint namespace.
- **`dependencies.py`** — `Checkpointer` type annotation for FastAPI dependency injection.

### Routers (`app/routers/`)

- **`items.py`** — Simple CRUD with an in-memory dict (placeholder, no real database).
- **`agent.py`** — `/api/agent/chat` (POST), `/api/agent/threads/{thread_id}/history` (GET), `/api/agent/threads/{thread_id}/state` (GET), `/api/agent/threads/{thread_id}` (DELETE). All routes share the `CheckpointerManager` from app state, building a fresh graph per request to ensure the latest compiled graph is used.

### Configuration (`app/config.py`)

`Settings` class via `pydantic-settings`, reads from `.env`. Key settings:
- `mcp_config_path` — path to MCP server config JSON (default: `mcp_servers.json`)
- `checkpointer_enabled` — whether to connect to PostgreSQL for agent state persistence (default: `false`; set to `true` and provide a valid `checkpointer_dsn` when needed)
- `checkpointer_dsn` — PostgreSQL connection string for LangGraph checkpointing
- `checkpointer_auto_setup` — whether to auto-create checkpoint tables on startup (default: true)

### Windows

`run.py` sets `asyncio.WindowsSelectorEventLoopPolicy()` before importing uvicorn — required by psycopg (the PostgreSQL driver). Always use `uv run python run.py` on Windows.

### Dependency Injection Pattern

The codebase uses `Annotated[Type, Depends(fn)]` type aliases (e.g., `MCPManager`, `Checkpointer`) declared in each subsystem's `dependencies.py`. Route handlers use these as parameter type annotations — FastAPI resolves them via `app.state`.