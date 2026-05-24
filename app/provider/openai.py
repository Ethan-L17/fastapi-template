"""OpenAI 兼容的大模型调用客户端。

不依赖 ``openai`` SDK，使用 ``httpx`` 直接调用 OpenAI 兼容的 ``/v1/chat/completions``
接口。返回 ``langchain_core.messages`` 中的消息对象，可直接用于 LangGraph / LangChain。

使用示例::

    from app.provider.openai import ChatOpenAI

    llm = ChatOpenAI(
        model="gpt-4o",
        api_key="sk-xxx",
        base_url="https://api.openai.com/v1",  # 或任何 OpenAI 兼容地址
    )

    # 同步调用
    response: AIMessage = await llm.ainvoke([HumanMessage(content="你好")])

    # 带工具调用
    tools = [{"type": "function", "function": {"name": "get_weather", ...}}]
    llm_with_tools = ChatOpenAI(model="gpt-4o", api_key="sk-xxx", tools=tools)
    response = await llm_with_tools.ainvoke([HumanMessage(content="北京天气如何")])
    if response.tool_calls:
        print(response.tool_calls)

    # 流式调用
    async for chunk in llm.astream([HumanMessage(content="讲个故事")]):
        print(chunk.content, end="")
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage

logger = logging.getLogger(__name__)


def _convert_messages_to_openai(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """将 langchain_core 消息列表转换为 OpenAI messages 格式。"""
    result: list[dict[str, Any]] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None) or msg.__class__.__name__.lower()

        if msg_type == "system":
            result.append({"role": "system", "content": msg.content})

        elif msg_type == "human":
            result.append({"role": "user", "content": msg.content})

        elif msg_type == "ai":
            entry: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": (
                                json.dumps(tc["args"], ensure_ascii=False)
                                if isinstance(tc["args"], dict)
                                else tc["args"]
                            ),
                        },
                    }
                    for tc in tool_calls
                ]
            result.append(entry)

        elif msg_type == "tool":
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(msg, "tool_call_id", ""),
                    "content": msg.content,
                }
            )

        else:
            # 兜底：当作 user 消息
            result.append({"role": "user", "content": str(msg.content)})

    return result


def _parse_tool_calls(raw_tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """将 OpenAI 响应中的 tool_calls 解析为 langchain_core 格式。"""
    if not raw_tool_calls:
        return []
    parsed: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        func = tc.get("function", {})
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str)
        except (json.JSONDecodeError, TypeError):
            args = {}
        parsed.append(
            {
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "args": args,
            }
        )
    return parsed


class ChatOpenAI:
    """OpenAI 兼容的聊天模型客户端。

    参数:
        model: 模型名称，如 ``"gpt-4o"``、``"deepseek-chat"``。
        api_key: API 密钥。
        base_url: API 基础地址，不含 ``/v1`` 后缀。默认 ``https://api.openai.com/v1``。
        temperature: 采样温度。
        max_tokens: 最大输出 token 数。
        top_p: 核采样参数。
        tools: OpenAI 格式的工具定义列表，用于 function calling。
        timeout: HTTP 请求超时秒数。
        extra_headers: 额外的 HTTP 请求头。
        **extra_kwargs: 其他传递给 API 的参数。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
        **extra_kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.tools = tools
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.extra_kwargs = extra_kwargs

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.tools:
            payload["tools"] = self.tools
        payload.update(self.extra_kwargs)
        return payload

    # ------------------------------------------------------------------
    # 非流式调用
    # ------------------------------------------------------------------

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
        """调用模型并返回一条完整的 ``AIMessage``。

        参数:
            messages: langchain_core 消息列表。
            **kwargs: 覆盖构造时的参数（如 ``temperature``、``max_tokens``）。

        返回:
            ``AIMessage``，包含 content、tool_calls、usage_metadata 等字段。
        """
        openai_messages = _convert_messages_to_openai(messages)

        # 允许每次调用覆盖参数
        temp = kwargs.pop("temperature", self.temperature)
        max_tok = kwargs.pop("max_tokens", self.max_tokens)
        top = kwargs.pop("top_p", self.top_p)
        tools = kwargs.pop("tools", self.tools)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temp,
            "stream": False,
        }
        if max_tok is not None:
            payload["max_tokens"] = max_tok
        if top is not None:
            payload["top_p"] = top
        if tools:
            payload["tools"] = tools
        if kwargs:
            payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url, json=payload, headers=self._build_headers()
            )
            resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> AIMessage:
        """将 OpenAI 响应 JSON 解析为 ``AIMessage``。"""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "") or ""
        raw_tool_calls = message.get("tool_calls")
        tool_calls = _parse_tool_calls(raw_tool_calls)

        usage = data.get("usage")
        usage_metadata = None
        if usage:
            usage_metadata = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return AIMessage(
            content=content,
            tool_calls=tool_calls if tool_calls else [],
            usage_metadata=usage_metadata,
            response_metadata={
                "model": data.get("model", ""),
                "finish_reason": choice.get("finish_reason", ""),
            },
        )

    # ------------------------------------------------------------------
    # 流式调用
    # ------------------------------------------------------------------

    async def astream(
        self, messages: list[BaseMessage], **kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]:
        """流式调用模型，逐块返回 ``AIMessageChunk``。

        参数:
            messages: langchain_core 消息列表。
            **kwargs: 覆盖构造时的参数。

        用法::

            async for chunk in llm.astream([HumanMessage(content="你好")]):
                print(chunk.content, end="")
        """
        openai_messages = _convert_messages_to_openai(messages)

        temp = kwargs.pop("temperature", self.temperature)
        max_tok = kwargs.pop("max_tokens", self.max_tokens)
        top = kwargs.pop("top_p", self.top_p)
        tools = kwargs.pop("tools", self.tools)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temp,
            "stream": True,
        }
        if max_tok is not None:
            payload["max_tokens"] = max_tok
        if top is not None:
            payload["top_p"] = top
        if tools:
            payload["tools"] = tools
        if kwargs:
            payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", url, json=payload, headers=self._build_headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    chunk = self._parse_stream_chunk(data)
                    if chunk is not None:
                        yield chunk

    def _parse_stream_chunk(self, data: dict[str, Any]) -> AIMessageChunk | None:
        """将一个 SSE chunk 解析为 ``AIMessageChunk``。"""
        choices = data.get("choices")
        if not choices:
            return None
        delta = choices[0].get("delta", {})

        content = delta.get("content", "") or ""
        raw_tool_calls = delta.get("tool_calls")
        tool_calls = _parse_tool_calls(raw_tool_calls) if raw_tool_calls else []

        return AIMessageChunk(
            content=content,
            tool_calls=tool_calls if tool_calls else [],
            response_metadata={
                "finish_reason": choices[0].get("finish_reason", ""),
            },
        )

    # ------------------------------------------------------------------
    # LangChain 兼容接口
    # ------------------------------------------------------------------

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
        """同步调用（内部委托给 ``ainvoke``，需在事件循环中调用）。"""
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self.ainvoke(messages, **kwargs)
        )

    def bind_tools(self, tools: list[dict[str, Any]]) -> "ChatOpenAI":
        """绑定工具定义，返回一个新的 ``ChatOpenAI`` 实例（不修改当前实例）。

        参数:
            tools: OpenAI 格式的工具定义列表。

        返回:
            绑定了工具的新 ``ChatOpenAI`` 实例。
        """
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            tools=tools,
            timeout=self.timeout,
            extra_headers=self.extra_headers,
            **self.extra_kwargs,
        )

    def with_config(self, **kwargs: Any) -> "ChatOpenAI":
        """返回一个带有覆盖配置的新实例。

        支持嵌套 config 格式：``llm.with_config(configurable={"model": "gpt-4o"})``
        或平铺格式：``llm.with_config(model="gpt-4o")``。
        """
        configurable = kwargs.pop("configurable", {})
        merged = {**self.__dict__, **configurable, **kwargs}
        return ChatOpenAI(
            model=merged.get("model", self.model),
            api_key=merged.get("api_key", self.api_key),
            base_url=merged.get("base_url", self.base_url),
            temperature=merged.get("temperature", self.temperature),
            max_tokens=merged.get("max_tokens", self.max_tokens),
            top_p=merged.get("top_p", self.top_p),
            tools=merged.get("tools", self.tools),
            timeout=merged.get("timeout", self.timeout),
            extra_headers=merged.get("extra_headers", self.extra_headers),
        )

    def __repr__(self) -> str:
        return (
            f"ChatOpenAI(model={self.model!r}, "
            f"base_url={self.base_url!r}, "
            f"temperature={self.temperature})"
        )
