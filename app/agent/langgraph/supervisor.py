"""LangGraph Supervisor 多 Agent 协作示例。

Supervisor 模式：一个 supervisor 节点根据用户意图把任务路由给不同的 worker agent，
worker 完成后返回 supervisor，由 supervisor 决定是继续调用其他 worker 还是回复用户。

本示例包含两个 worker：
- **researcher** — 负责信息检索 / 知识问答
- **mathematician** — 负责数学计算

使用 ``ChatOpenAI``（``app.provider.openai``）作为 LLM 后端，兼容任何 OpenAI API。

使用示例::

    from app.agent.langgraph.supervisor import build_supervisor

    graph = build_supervisor(api_key="sk-xxx", base_url="https://api.openai.com/v1")

    # 非流式
    result = await graph.ainvoke({"messages": [("user", "帮我算一下 123 * 456")]})

    # 流式（获取每个节点的输出更新）
    async for event in graph.astream({"messages": [("user", "你好")]}, stream_mode="updates"):
        print(event)
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent.langgraph.checkpointer import CheckpointerManager
from app.provider.openai import ChatOpenAI

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "supervisor"

# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """你是一个任务调度 supervisor。根据用户的问题，决定应该交给哪个 worker 来处理。

可选的 worker：
- researcher: 负责信息检索、知识问答、事实查询
- mathematician: 负责数学计算、公式推导、数值分析

请用 JSON 格式回复，包含一个 "next" 字段，值为 worker 名称或 "FINISH"。
- 如果需要某个 worker 处理：{{"next": "researcher"}} 或 {{"next": "mathematician"}}
- 如果已经得到足够信息可以直接回复用户：{{"next": "FINISH"}}

只输出 JSON，不要输出其他内容。"""

WORKER_SYSTEM_PROMPTS = {
    "researcher": "你是一个信息检索专家。根据用户的问题，给出准确、详细的回答。请直接给出答案，不需要调用工具。",
    "mathematician": "你是一个数学计算专家。根据用户的问题，进行精确的计算和分析。请直接给出计算过程和结果。",
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class SupervisorState(TypedDict):
    """Supervisor graph 的运行时状态。"""
    messages: Annotated[list, add_messages]
    next_worker: str  # supervisor 决定的下一个 worker，或 "FINISH"


# ---------------------------------------------------------------------------
# 节点实现
# ---------------------------------------------------------------------------

def _build_llm(
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """构建 LLM 实例。"""
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _parse_supervisor_response(content: str) -> str:
    """解析 supervisor 的 JSON 响应，提取 next_worker。"""
    text = content.strip()
    # 处理可能被 markdown 包裹的情况
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        parsed = json.loads(text)
        return parsed.get("next", "FINISH")
    except (json.JSONDecodeError, AttributeError):
        lower = text.lower()
        if "researcher" in lower:
            return "researcher"
        if "mathematician" in lower:
            return "mathematician"
        return "FINISH"


async def supervisor_node(
    state: SupervisorState,
    *,
    llm: ChatOpenAI,
) -> dict[str, Any]:
    """Supervisor 节点：分析消息，决定路由到哪个 worker。"""
    messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + list(state["messages"])
    response: AIMessage = await llm.ainvoke(messages)

    next_worker = _parse_supervisor_response(response.content)
    logger.info("Supervisor decided: next_worker=%s", next_worker)

    # 把 supervisor 的决策也加到消息中，方便 worker 理解上下文
    return {
        "next_worker": next_worker,
        "messages": [AIMessage(content=f"[routing to: {next_worker}]")],
    }


async def researcher_node(
    state: SupervisorState,
    *,
    llm: ChatOpenAI,
) -> dict[str, Any]:
    """Researcher worker 节点。"""
    messages = [SystemMessage(content=WORKER_SYSTEM_PROMPTS["researcher"])] + list(state["messages"])
    response: AIMessage = await llm.ainvoke(messages)
    return {"messages": [response]}


async def mathematician_node(
    state: SupervisorState,
    *,
    llm: ChatOpenAI,
) -> dict[str, Any]:
    """Mathematician worker 节点。"""
    messages = [SystemMessage(content=WORKER_SYSTEM_PROMPTS["mathematician"])] + list(state["messages"])
    response: AIMessage = await llm.ainvoke(messages)
    return {"messages": [response]}


def route_next(state: SupervisorState) -> Literal["researcher", "mathematician", "__end__"]:
    """条件路由：根据 supervisor 的决定分发到对应 worker 或结束。"""
    next_worker = state.get("next_worker", "FINISH")
    if next_worker == "researcher":
        return "researcher"
    elif next_worker == "mathematician":
        return "mathematician"
    return "__end__"


# ---------------------------------------------------------------------------
# Graph 构建
# ---------------------------------------------------------------------------

def build_supervisor(
    *,
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    checkpointer: CheckpointerManager | None = None,
):
    """构建并编译 supervisor graph。

    参数:
        api_key: OpenAI API key。
        base_url: OpenAI 兼容 API 地址。
        model: 模型名称。
        temperature: 采样温度。
        max_tokens: 最大输出 token 数。
        checkpointer: 可选的 PostgreSQL checkpointer，用于状态持久化。

    返回:
        编译好的 LangGraph graph。
    """
    llm = _build_llm(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    builder = StateGraph(SupervisorState)

    # 添加节点
    builder.add_node("supervisor", lambda state: supervisor_node(state, llm=llm))
    builder.add_node("researcher", lambda state: researcher_node(state, llm=llm))
    builder.add_node("mathematician", lambda state: mathematician_node(state, llm=llm))

    # 路由：START -> supervisor -> (worker | END) -> supervisor
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "researcher": "researcher",
            "mathematician": "mathematician",
            "__end__": END,
        },
    )
    builder.add_edge("researcher", "supervisor")
    builder.add_edge("mathematician", "supervisor")

    kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer.checkpointer

    return builder.compile(**kwargs)


def build_config(manager: CheckpointerManager, thread_id: str) -> dict:
    """该工作流专用的 config 构造器。"""
    return manager.build_config(workflow=WORKFLOW_NAME, thread_id=thread_id)
