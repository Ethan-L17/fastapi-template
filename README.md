# FastAPI Project

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn main:app --reload

# 安装开发依赖
uv sync --group dev
```

## API 文档

启动服务器后访问：

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## MCP Client 集成

本项目作为 MCP **Client** 连接外部 MCP Server，支持 **stdio** 和 **SSE** 两种传输方式。

### 配置

编辑项目根目录的 `mcp_servers.json`，添加要连接的 MCP 服务器：

```json
{
  "mcpServers": {
    "my-stdio-server": {
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "env": {},
      "enabled": true,
      "timeout": 30
    },
    "my-remote-server": {
      "transport": "sse",
      "url": "http://localhost:3001/sse",
      "headers": { "Authorization": "Bearer token" },
      "enabled": true,
      "timeout": 30
    }
  }
}
```

也可以通过环境变量 `MCP_CONFIG_PATH` 指定其他路径。

### MCP API 接口

| 方法   | 路径                                  | 说明                   |
| ------ | ------------------------------------- | ---------------------- |
| GET    | `/api/mcp/servers`                    | 列出已连接的 MCP 服务器 |
| GET    | `/api/mcp/servers/{name}/tools`       | 列出服务器暴露的工具    |
| POST   | `/api/mcp/tools/call`                 | 调用指定服务器的工具    |
| GET    | `/api/mcp/servers/{name}/resources`   | 列出服务器的资源        |
| POST   | `/api/mcp/resources/read`             | 读取指定资源            |
| POST   | `/api/mcp/servers/reload`             | 热重载全部服务器配置    |
| POST   | `/api/mcp/servers/{name}/reconnect`   | 重连指定服务器          |

### 架构设计

```
mcp_servers.json ──▶ FileConfigProvider ──┐
                                          ├──▶ MCPClientManager ──▶ API Routes
(future) Database ──▶ DatabaseConfigProvider ─┘
```

- **MCPConfigProvider** 抽象基类：定义 `load_servers()` 接口
- **FileConfigProvider**：从 JSON 文件加载配置（当前默认）
- **DatabaseConfigProvider**：预留占位，实现后可从数据库动态获取配置
- **MCPClientManager**：管理所有 MCP 连接的生命周期，支持热重载

## 项目结构

```
├── main.py              # 应用入口 + MCP 生命周期管理
├── mcp_servers.json     # MCP 服务器配置文件
├── app/
│   ├── config.py        # 应用配置
│   ├── mcp/
│   │   ├── config.py    # MCP 配置模型与 Provider
│   │   ├── client.py    # MCP 客户端连接管理器
│   │   └── router.py    # MCP API 路由
│   ├── models/          # 数据模型
│   ├── schemas/         # Pydantic 模式
│   └── routers/         # 业务路由
├── pyproject.toml       # 项目配置与依赖
└── uv.lock              # 锁定文件
```
