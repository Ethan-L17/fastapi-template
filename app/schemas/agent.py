from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str = Field(..., description="会话 / 用户维度的标识，用作 checkpoint 的 thread_id")
    message: str = Field(..., description="用户本轮输入")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    thread_id: str
    workflow: str
    messages: list[ChatMessage]


class HistoryItem(BaseModel):
    checkpoint_id: str
    step: int | None = None
    messages: list[ChatMessage]
