from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FastAPI Project"
    debug: bool = False
    mcp_config_path: str = "mcp_servers.json"

    # --- LangGraph checkpointer (PostgreSQL) ---
    # 假链接占位，实际部署时通过环境变量 / .env 覆盖。
    # 形如: postgresql://user:password@host:5432/dbname
    checkpointer_dsn: str = (
        "postgresql://langgraph_user:langgraph_pass@localhost:5432/langgraph_db"
    )
    checkpointer_pool_min_size: int = 1
    checkpointer_pool_max_size: int = 10
    checkpointer_pool_timeout: float = 30.0
    # 启动时是否自动执行 checkpointer 建表语句
    checkpointer_auto_setup: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
