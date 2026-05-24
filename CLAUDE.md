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

# Run a single test file
uv run pytest tests/test_items.py

# Run a single test by name
uv run pytest -k <test_name>

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

### Agent System (`app/agent/`)

Agent 实现按框架依赖分成两个子目录：

- **`langgraph/`** — 依赖 LangGraph / LangChain 框架的 agent
  - `checkpointer.py` — `CheckpointerManager` wraps `psycopg`'s `AsyncConnectionPool` and `AsyncPostgresSaver`. Each workflow is isolated via `checkpoint_ns`. Call `build_config(workflow, thread_id)` to get the LangGraph config dict.
  - `react.py` — Builds a ReAct agent `StateGraph` (agent → conditional → tools → agent). The graph nodes are **mock placeholders** — replace `_call_model` with a real LLM call and `_call_tools` with actual tool execution. `WORKFLOW_NAME = "react_agent"` is the checkpoint namespace.
  - `dependencies.py` — `Checkpointer` type annotation for FastAPI dependency injection.
- **`standalone/`** — 不依赖特定框架的 agent（placeholder，待实现）

### LLM Provider (`app/provider/`)

- **`openai.py`** — `ChatOpenAI` 类，不依赖 `openai` SDK，使用 `httpx` 直接调用 OpenAI 兼容的 `/v1/chat/completions` 接口。返回 `langchain_core.messages` 中的消息对象（`AIMessage` / `AIMessageChunk`），可直接用于 LangGraph / LangChain。支持非流式（`ainvoke`）、流式（`astream`）、工具调用（`bind_tools`）。支持任何 OpenAI 兼容的 API 地址（通过 `base_url` 参数配置）。

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

### Tests (`tests/`)

使用 `pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`），所有测试函数直接定义为 `async def`。

- **`conftest.py`** — 共享夹具。`client` fixture 创建 mock 掉 MCP 连接和 PostgreSQL 的 FastAPI `httpx.AsyncClient` 测试客户端。
- **`test_health.py`** — 根路由和健康检查端点测试。
- **`test_items.py`** — Items CRUD 路由的完整测试（创建、查询、列表、删除、404）。
- **`test_openai_provider.py`** — `ChatOpenAI` 单元测试：消息格式转换、tool_calls 解析、实例化参数、`bind_tools` / `with_config`、mock HTTP 的 `ainvoke` 调用。
- **`test_mcp_server.py`** — 不是 pytest 测试，是独立的 MCP 测试服务器脚本（SSE/stdio 模式）。