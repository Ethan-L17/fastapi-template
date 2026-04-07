import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.mcp.client import MCPClientManager
from app.mcp.config import FileConfigProvider
from app.mcp.router import router as mcp_router
from app.routers import items

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: connect to configured MCP servers ---
    provider = FileConfigProvider(settings.mcp_config_path)
    # To switch to DB-based config in the future:
    #   from app.mcp.config import DatabaseConfigProvider
    #   provider = DatabaseConfigProvider(db_session)
    manager = MCPClientManager(provider)
    app.state.mcp_manager = manager
    await manager.start()
    logger.info("MCP client manager started (%d server(s))", len(manager.connections))

    yield

    # --- Shutdown: close all MCP connections ---
    await manager.stop()
    logger.info("MCP client manager stopped")


app = FastAPI(title="FastAPI Project", version="0.1.0", lifespan=lifespan)

app.include_router(items.router, prefix="/api")
app.include_router(mcp_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI Project"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
