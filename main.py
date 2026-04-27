import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.checkpointer import CheckpointerManager
from app.config import settings
from app.mcp.client import MCPClientManager
from app.mcp.config import FileConfigProvider
from app.mcp.router import router as mcp_router
from app.routers import agent as agent_router
from app.routers import items

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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

    # --- Startup: open shared LangGraph PostgreSQL checkpointer pool ---
    if settings.checkpointer_enabled:
        checkpointer = CheckpointerManager(
            dsn=settings.checkpointer_dsn,
            min_size=settings.checkpointer_pool_min_size,
            max_size=settings.checkpointer_pool_max_size,
            timeout=settings.checkpointer_pool_timeout,
            auto_setup=settings.checkpointer_auto_setup,
        )
        try:
            await checkpointer.setup()
            app.state.checkpointer = checkpointer
        except Exception:
            logger.warning(
                "Checkpointer setup failed (PostgreSQL unavailable?), "
                "agent routes will return 503"
            )
            app.state.checkpointer = None
    else:
        app.state.checkpointer = None

    yield

    # --- Shutdown: close checkpointer pool then MCP connections ---
    if app.state.checkpointer is not None:
        checkpointer = app.state.checkpointer
        await checkpointer.close()
    await manager.stop()
    logger.info("MCP client manager stopped")


app = FastAPI(title="FastAPI Project", version="0.1.0", lifespan=lifespan)

app.include_router(items.router, prefix="/api")
app.include_router(mcp_router, prefix="/api")
app.include_router(agent_router.router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI Project"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
