"""ReAct agent HTTP 路由示例。

演示如何利用共享的 ``CheckpointerManager`` 在不同请求间保留会话状态，
并通过 ``checkpoint_ns`` 区分不同工作流。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.agent.dependencies import Checkpointer
from app.agent.react import WORKFLOW_NAME, build_config, build_react_agent
from app.schemas.agent import ChatMessage, ChatRequest, ChatResponse, HistoryItem

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
    # AsyncPostgresSaver 暴露了 adelete_thread，会同时清掉 writes/blobs。
    # 注意：默认实现会删除该 thread_id 下所有 namespace 的记录。
    # 如果需要只清理本工作流的数据，可以按 (thread_id, checkpoint_ns) 自行执行 SQL。
    await checkpointer.checkpointer.adelete_thread(thread_id)
