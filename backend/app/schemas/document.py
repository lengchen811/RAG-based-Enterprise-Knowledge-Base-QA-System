"""文档相关请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_size: int
    status: str
    chunk_count: int
    error_msg: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentOut]


class DocumentStatusResponse(BaseModel):
    id: int
    status: str
    chunk_count: int
    error_msg: str | None

    model_config = {"from_attributes": True}