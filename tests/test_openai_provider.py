"""ChatOpenAI provider 单元测试（mock HTTP，不实际调用 API）。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.provider.openai import ChatOpenAI, _convert_messages_to_openai, _parse_tool_calls


# ------------------------------------------------------------------
# 辅助函数测试
# ------------------------------------------------------------------


class TestConvertMessages:
    def test_system_message(self):
        msgs = [SystemMessage(content="你是一个助手")]
        result = _convert_messages_to_openai(msgs)
        assert result == [{"role": "system", "content": "你是一个助手"}]

    def test_human_message(self):
        msgs = [HumanMessage(content="你好")]
        result = _convert_messages_to_openai(msgs)
        assert result == [{"role": "user", "content": "你好"}]

    def test_ai_message_plain(self):
        msgs = [AIMessage(content="你好呀")]
        result = _convert_messages_to_openai(msgs)
        assert result == [{"role": "assistant", "content": "你好呀"}]

    def test_ai_message_with_tool_calls(self):
        msgs = [
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "search", "args": {"q": "test"}}],
            )
        ]
        result = _convert_messages_to_openai(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"][0]["id"] == "c1"
        assert result[0]["tool_calls"][0]["function"]["name"] == "search"
        assert json.loads(result[0]["tool_calls"][0]["function"]["arguments"]) == {"q": "test"}

    def test_tool_message(self):
        msgs = [ToolMessage(content="结果", tool_call_id="c1")]
        result = _convert_messages_to_openai(msgs)
        assert result == [{"role": "tool", "tool_call_id": "c1", "content": "结果"}]

    def test_mixed_messages(self):
        msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
        ]
        result = _convert_messages_to_openai(msgs)
        assert len(result) == 3
        assert [m["role"] for m in result] == ["system", "user", "assistant"]


class TestParseToolCalls:
    def test_empty(self):
        assert _parse_tool_calls(None) == []
        assert _parse_tool_calls([]) == []

    def test_single(self):
        raw = [
            {"id": "c1", "function": {"name": "get_weather", "arguments": '{"city":"北京"}'}}
        ]
        result = _parse_tool_calls(raw)
        assert len(result) == 1
        assert result[0]["id"] == "c1"
        assert result[0]["name"] == "get_weather"
        assert result[0]["args"] == {"city": "北京"}

    def test_invalid_json_args(self):
        raw = [{"id": "c2", "function": {"name": "bad", "arguments": "not-json"}}]
        result = _parse_tool_calls(raw)
        assert result[0]["args"] == {}


# ------------------------------------------------------------------
# ChatOpenAI 实例化测试
# ------------------------------------------------------------------


class TestChatOpenAIInit:
    def test_defaults(self):
        llm = ChatOpenAI()
        assert llm.model == "gpt-4o-mini"
        assert llm.temperature == 0.7
        assert llm.base_url == "https://api.openai.com/v1"
        assert llm.tools is None

    def test_custom_params(self):
        llm = ChatOpenAI(
            model="deepseek-chat",
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1/",
            temperature=0.1,
            max_tokens=1024,
        )
        assert llm.model == "deepseek-chat"
        assert llm.base_url == "https://api.deepseek.com/v1"  # trailing slash stripped
        assert llm.max_tokens == 1024

    def test_repr(self):
        llm = ChatOpenAI(model="m", base_url="http://x")
        r = repr(llm)
        assert "m" in r
        assert "http://x" in r


class TestChatOpenAIBindTools:
    def test_bind_tools_creates_new_instance(self):
        llm = ChatOpenAI(model="gpt-4o")
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        llm2 = llm.bind_tools(tools)
        assert llm.tools is None
        assert llm2.tools == tools
        assert llm2.model == "gpt-4o"
        assert llm is not llm2


class TestChatOpenAIWithConfig:
    def test_flat_kwargs(self):
        llm = ChatOpenAI(model="a")
        llm2 = llm.with_config(model="b", temperature=0.1)
        assert llm2.model == "b"
        assert llm2.temperature == 0.1
        assert llm.model == "a"  # 原实例不变

    def test_configurable_dict(self):
        llm = ChatOpenAI(model="a")
        llm2 = llm.with_config(configurable={"model": "c"})
        assert llm2.model == "c"


# ------------------------------------------------------------------
# ainvoke 测试（mock HTTP）
# ------------------------------------------------------------------


def _make_openai_response(content="hello", tool_calls=None, usage=None):
    """构造一个 OpenAI 格式的响应 dict。"""
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    resp = {
        "id": "chatcmpl-test",
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
    }
    if usage:
        resp["usage"] = usage
    return resp


class TestChatOpenAIInvoke:
    @pytest.fixture
    def llm(self):
        return ChatOpenAI(model="gpt-4o", api_key="sk-test")

    async def test_basic_invoke(self, llm):
        mock_resp_data = _make_openai_response(content="你好呀")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_resp_data)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await llm.ainvoke([HumanMessage(content="你好")])

        assert isinstance(result, AIMessage)
        assert result.content == "你好呀"
        assert result.tool_calls == []

    async def test_invoke_with_tool_calls(self, llm):
        tool_calls_raw = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city":"北京"}'},
            }
        ]
        mock_resp_data = _make_openai_response(content="", tool_calls=tool_calls_raw)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_resp_data)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await llm.ainvoke([HumanMessage(content="北京天气")])

        assert result.tool_calls
        assert result.tool_calls[0]["name"] == "get_weather"
        assert result.tool_calls[0]["args"] == {"city": "北京"}

    async def test_invoke_with_usage(self, llm):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        mock_resp_data = _make_openai_response(content="ok", usage=usage)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_resp_data)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await llm.ainvoke([HumanMessage(content="hi")])

        assert result.usage_metadata["input_tokens"] == 10
        assert result.usage_metadata["output_tokens"] == 5
        assert result.usage_metadata["total_tokens"] == 15

    async def test_invoke_passes_temperature_override(self, llm):
        mock_resp_data = _make_openai_response(content="ok")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_resp_data)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            await llm.ainvoke([HumanMessage(content="hi")], temperature=0.1)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["temperature"] == 0.1
