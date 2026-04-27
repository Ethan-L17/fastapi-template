from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FastAPI Project"
    debug: bool = False
    mcp_config_path: str = "mcp_servers.json"

    # --- LangGraph checkpointer (PostgreSQL) ---
    # 默认禁用；需要持久化 agent 状态时设为 true 并提供有效的 checkpointer_dsn
    checkpointer_enabled: bool = False
    # 形如: postgresql://user:password@host:5432/dbname
    checkpointer_dsn: str = (
        "postgresql://langgraph_user:langgraph_pass@localhost:5432/langgraph_db"
    )
    checkpointer_pool_min_size: int = 1
    checkpointer_pool_max_size: int = 10
    checkpointer_pool_timeout: float = 5.0
    checkpointer_auto_setup: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
