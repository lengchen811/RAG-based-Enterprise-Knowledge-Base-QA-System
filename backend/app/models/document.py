"""文档表：包含处理状态机（PENDING/PROCESSING/COMPLETED/FAILED）。"""
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentStatus(str, Enum):
    """文档处理状态机。"""

    PENDING = "PENDING"        # 已接收，等待处理
    PROCESSING = "PROCESSING"  # 正在解析/向量化
    COMPLETED = "COMPLETED"    # 处理完成，可检索
    FAILED = "FAILED"          # 处理失败


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    owner = relationship("User", back_populates="documents")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"