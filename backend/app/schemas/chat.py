"""对话/会话相关请求、响应模型。"""
from datetime import datetime

from pydantic import BaseModel, Field


class ChatSource(BaseModel):
    """问答引用来源（支持前端点击高亮定位）。"""

    document_id: int
    filename: str
    chunk_index: int
    page: int | None = None
    score: float | None = None
    content_excerpt: str = ""


class ChatRequest(BaseModel):
    session_id: int | None = Field(default=None, description="空则新建会话")
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    sources: list[ChatSource]


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class SessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    total: int
    items: list[SessionOut]