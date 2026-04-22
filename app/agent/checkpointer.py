"""LangGraph PostgreSQL checkpointer 管理。

提供一个基于 `psycopg` 异步连接池的 `AsyncPostgresSaver`，并通过
`checkpoint_ns` (checkpoint namespace) 来区分不同工作流保存的 checkpoint。

典型用法::

    manager = CheckpointerManager(dsn=..., min_size=1, max_size=10)
    await manager.setup()

    graph = builder.compile(checkpointer=manager.checkpointer)

    config = manager.build_config(workflow="react_agent", thread_id="user-123")
    await graph.ainvoke(inputs, config=config)

    await manager.close()

不同工作流（例如 ``react_agent`` 与 ``summarizer``）会以不同的
``checkpoint_ns`` 写入同一张 checkpoint 表，在按 ``thread_id`` 查询时互不干扰。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)


# psycopg 连接参数：checkpointer 要求 autocommit + dict_row + prepare_threshold=0
# 参考 langgraph-checkpoint-postgres 官方建议。
_CONNECTION_KWARGS: dict[str, Any] = {
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
}


class CheckpointerManager:
    """管理 PostgreSQL checkpointer 的连接池与生命周期。"""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 30.0,
        auto_setup: bool = True,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._timeout = timeout
        self._auto_setup = auto_setup

        self._pool: Optional[AsyncConnectionPool] = None
        self._checkpointer: Optional[AsyncPostgresSaver] = None

    # ------------------------------------------------------------------ lifecycle

    async def setup(self) -> None:
        """创建连接池并初始化 checkpointer（含建表）。"""
        if self._pool is not None:
            return

        pool = AsyncConnectionPool(
            conninfo=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            timeout=self._timeout,
            kwargs=_CONNECTION_KWARGS,
            open=False,
        )
        await pool.open(wait=True)
        self._pool = pool

        self._checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]

        if self._auto_setup:
            # 首次启动时创建 checkpoints / checkpoint_writes / checkpoint_blobs 等表。
            # 后续运行是幂等的（内部会做版本迁移判断）。
            await self._checkpointer.setup()

        logger.info(
            "Checkpointer pool ready (min=%d, max=%d)", self._min_size, self._max_size
        )

    async def close(self) -> None:
        """关闭连接池。"""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
        self._checkpointer = None
        logger.info("Checkpointer pool closed")

    # ------------------------------------------------------------------ accessors

    @property
    def checkpointer(self) -> AsyncPostgresSaver:
        if self._checkpointer is None:
            raise RuntimeError(
                "CheckpointerManager 尚未初始化，请先 await manager.setup()"
            )
        return self._checkpointer

    @property
    def pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            raise RuntimeError(
                "CheckpointerManager 尚未初始化，请先 await manager.setup()"
            )
        return self._pool

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def build_config(
        workflow: str,
        thread_id: str,
        *,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构造 LangGraph 调用时的 config，通过 ``checkpoint_ns`` 区分工作流。

        :param workflow: 工作流名称，会写入 ``checkpoint_ns`` 字段，用于区分
            同一数据库下的不同 graph 的 checkpoint。
        :param thread_id: 会话 / 用户维度的标识，例如 ``user-123`` 或
            ``session-abc``。
        :param extra: 需要额外透传给 ``configurable`` 的键值。
        """
        configurable: dict[str, Any] = {
            "thread_id": thread_id,
            "checkpoint_ns": workflow,
        }
        if extra:
            configurable.update(extra)
        return {"configurable": configurable}
