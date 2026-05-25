"""一个使用 PostgreSQL checkpointer 做长期记忆的 ReAct agent 示例。

该模块只负责 **构建 graph**，真正的 checkpointer / 连接池由
``app.agent.langgraph.checkpointer.CheckpointerManager`` 在应用启动时创建并注入，
这样不同工作流可以共享同一个连接池。

使用示例::

    from app.agent.langgraph.react import build_react_agent
    from app.agent.langgraph.checkpointer import CheckpointerManager

    manager: CheckpointerManager = app.state.checkpointer  # 由 lifespan 注入
    graph = build_react_agent(manager)

    config = manager.build_config(workflow="react_agent", thread_id="user-123")
    result = await graph.ainvoke({"messages": [("user", "你好")]}, config=config)
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent.langgraph.checkpointer import CheckpointerManager

# 工作流名称，会作为 checkpoint_ns 写入数据库
WORKFLOW_NAME = "react_agent"


class AgentState(TypedDict):
    """ReAct agent 的运行时状态。"""

    messages: Annotated[list, add_messages]


async def _call_model(state: AgentState) -> AgentState:
    """调用 LLM 的节点占位实现。

    真实项目里可以换成 ``ChatOpenAI`` / ``ChatAnthropic`` 等绑定了工具的模型，
    并返回可能包含 tool_calls 的 AIMessage。
    """
    last = state["messages"][-1] if state["messages"] else None
    user_text = getattr(last, "content", None) or (last[1] if isinstance(last, tuple) else "")
    reply = f"[mock-llm] received: {user_text}"
    return {"messages": [("assistant", reply)]}


async def _call_tools(state: AgentState) -> AgentState:
    """工具调用节点占位实现。"""
    return {"messages": [("tool", "[mock-tool] no-op")]}


def _should_continue(state: AgentState) -> str:
    """决定是否继续调用工具。占位实现总是结束。"""
    return END


def build_react_agent(manager: CheckpointerManager | None = None):
    """构建并编译 ReAct graph。有 PostgreSQL checkpointer 时绑定持久化，否则用内存。"""
    builder = StateGraph(AgentState)
    builder.add_node("agent", _call_model)
    builder.add_node("tools", _call_tools)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        _should_continue,
        {END: END, "tools": "tools"},
    )
    builder.add_edge("tools", "agent")

    kwargs = {}
    if manager is not None:
        kwargs["checkpointer"] = manager.checkpointer
    return builder.compile(**kwargs)


def build_config(manager: CheckpointerManager | None, thread_id: str) -> dict:
    """该工作流专用的 config 构造器，固定使用 ``WORKFLOW_NAME`` 作为命名空间。"""
    if manager is None:
        return {"configurable": {"thread_id": thread_id}}
    return manager.build_config(workflow=WORKFLOW_NAME, thread_id=thread_id)
