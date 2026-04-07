from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FastAPI Project"
    debug: bool = False
    mcp_config_path: str = "mcp_servers.json"

    class Config:
        env_file = ".env"


settings = Settings()
