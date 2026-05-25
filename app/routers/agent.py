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
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="Checkpointer not available (PostgreSQL not connected)")
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
        checkpointer=checkpointer,  # type: ignore[arg-type]
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
    """与 Supervisor agent 对话（SSE 真流式输出，token 级别）。"""

    async def event_generator():
        graph = _build_supervisor_graph(checkpointer)
        config = build_supervisor_config(checkpointer, thread_id=req.thread_id)

        try:
            async for msg, metadata in graph.astream(
                {"messages": [("user", req.message)]},
                config=config,
                stream_mode="messages",
            ):
                node_name = metadata.get("langgraph_node", "")

                # 只处理 LLM 产出的 AIMessageChunk / AIMessage
                content = getattr(msg, "content", "")
                if not content:
                    continue

                # supervisor 的路由决策消息（[routing to: xxx]）提取为 routing 事件
                if node_name == "supervisor" and content.startswith("[routing"):
                    # 从内容中提取 next_worker
                    next_worker = content.replace("[routing to: ", "").rstrip("]")
                    yield f"data: {json.dumps({'node': 'supervisor', 'type': 'routing', 'content': next_worker}, ensure_ascii=False)}\n\n"
                    continue

                # 其他内容（LLM token 或完整消息）都作为 token 事件输出
                yield f"data: {json.dumps({'node': node_name, 'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"

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
