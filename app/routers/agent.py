"""Agent HTTP 路由。

提供 ReAct agent 和 Supervisor agent 的对话接口，支持非流式和 SSE 流式输出。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.langgraph.checkpointer import CheckpointerManager
from app.agent.langgraph.dependencies import Checkpointer
from app.agent.langgraph.react import WORKFLOW_NAME, build_config, build_react_agent
from app.agent.langgraph.supervisor import (
    WORKFLOW_NAME as SUPERVISOR_WORKFLOW_NAME,
    build_config as build_supervisor_config,
    build_supervisor,
)
from app.schemas.agent import ChatMessage, ChatRequest, ChatResponse, HistoryItem
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _to_chat_message(msg: Any) -> ChatMessage:
    """把 LangGraph 里的消息（BaseMessage 或 tuple）转成 API 响应格式。"""
    if isinstance(msg, tuple) and len(msg) == 2:
        role, content = msg
        return ChatMessage(role=str(role), content=str(content))

    role = getattr(msg, "type", None) or getattr(msg, "role", None) or "assistant"
    content = getattr(msg, "content", "")
    if not isinstance(content, str):
        content = str(content)
    return ChatMessage(role=str(role), content=content)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, checkpointer: Checkpointer) -> ChatResponse:
    """与 ReAct agent 对话一次，状态会按 ``thread_id`` 持久化到 PostgreSQL。"""
    graph = build_react_agent(checkpointer)
    config = build_config(checkpointer, thread_id=req.thread_id)

    result = await graph.ainvoke({"messages": [("user", req.message)]}, config=config)

    return ChatResponse(
        thread_id=req.thread_id,
        workflow=WORKFLOW_NAME,
        messages=[_to_chat_message(m) for m in result.get("messages", [])],
    )


@router.get("/threads/{thread_id}/history", response_model=list[HistoryItem])
async def get_history(thread_id: str, checkpointer: Checkpointer) -> list[HistoryItem]:
    """返回某个 thread 在本工作流下的全部 checkpoint 历史。"""
    graph = build_react_agent(checkpointer)
    config = build_config(checkpointer, thread_id=thread_id)

    history: list[HistoryItem] = []
    async for snapshot in graph.aget_state_history(config):
        values = snapshot.values or {}
        messages = values.get("messages", []) if isinstance(values, dict) else []
        history.append(
            HistoryItem(
                checkpoint_id=snapshot.config["configurable"].get("checkpoint_id", ""),
                step=snapshot.metadata.get("step") if snapshot.metadata else None,
                messages=[_to_chat_message(m) for m in messages],
            )
        )
    return history


@router.get("/threads/{thread_id}/state", response_model=ChatResponse)
async def get_state(thread_id: str, checkpointer: Checkpointer) -> ChatResponse:
    """返回某个 thread 当前最新的状态。"""
    graph = build_react_agent(checkpointer)
    config = build_config(checkpointer, thread_id=thread_id)

    snapshot = await graph.aget_state(config)
    if snapshot is None or not snapshot.values:
        raise HTTPException(status_code=404, detail="thread state not found")

    messages = snapshot.values.get("messages", []) if isinstance(snapshot.values, dict) else []
    return ChatResponse(
        thread_id=thread_id,
        workflow=WORKFLOW_NAME,
        messages=[_to_chat_message(m) for m in messages],
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, checkpointer: Checkpointer) -> None:
    """删除某个 thread 在本工作流下的所有 checkpoint。"""
    await checkpointer.checkpointer.adelete_thread(thread_id)


# ---------------------------------------------------------------------------
# Supervisor agent 路由
# ---------------------------------------------------------------------------

def _build_supervisor_graph(checkpointer: CheckpointerManager | None = None):
    """根据配置构建 supervisor graph。"""
    return build_supervisor(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        checkpointer=checkpointer,
    )


@router.post("/supervisor/chat", response_model=ChatResponse)
async def supervisor_chat(req: ChatRequest, checkpointer: Checkpointer) -> ChatResponse:
    """与 Supervisor agent 对话一次（非流式）。"""
    graph = _build_supervisor_graph(checkpointer)
    config = build_supervisor_config(checkpointer, thread_id=req.thread_id)

    result = await graph.ainvoke({"messages": [("user", req.message)]}, config=config)

    return ChatResponse(
        thread_id=req.thread_id,
        workflow=SUPERVISOR_WORKFLOW_NAME,
        messages=[_to_chat_message(m) for m in result.get("messages", [])],
    )


@router.post("/supervisor/chat/stream")
async def supervisor_chat_stream(req: ChatRequest, checkpointer: Checkpointer) -> StreamingResponse:
    """与 Supervisor agent 对话（SSE 流式输出）。

    返回 Server-Sent Events 流，每个事件格式：
    ```
    data: {"node": "supervisor", "type": "routing", "content": "researcher"}
    data: {"node": "researcher", "type": "message", "content": "..."}
    data: {"node": "supervisor", "type": "final", "content": "..."}
    ```
    """

    async def event_generator():
        graph = _build_supervisor_graph(checkpointer)
        config = build_supervisor_config(checkpointer, thread_id=req.thread_id)

        try:
            async for event in graph.astream(
                {"messages": [("user", req.message)]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, node_output in event.items():
                    if node_name == "supervisor":
                        next_worker = node_output.get("next_worker", "FINISH")
                        yield f"data: {json.dumps({'node': 'supervisor', 'type': 'routing', 'content': next_worker}, ensure_ascii=False)}\n\n"

                        # 如果 supervisor 决定 FINISH，提取最终回复
                        if next_worker == "FINISH":
                            messages = node_output.get("messages", [])
                            for msg in messages:
                                content = getattr(msg, "content", None) or (msg[1] if isinstance(msg, tuple) else "")
                                if content and not content.startswith("[routing"):
                                    yield f"data: {json.dumps({'node': 'supervisor', 'type': 'final', 'content': content}, ensure_ascii=False)}\n\n"

                    elif node_name in ("researcher", "mathematician"):
                        messages = node_output.get("messages", [])
                        for msg in messages:
                            content = getattr(msg, "content", None) or (msg[1] if isinstance(msg, tuple) else "")
                            if content:
                                yield f"data: {json.dumps({'node': node_name, 'type': 'message', 'content': content}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("Supervisor stream error")
            yield f"data: {json.dumps({'node': 'error', 'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
