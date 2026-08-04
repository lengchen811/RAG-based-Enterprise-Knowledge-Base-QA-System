"""异步数据库引擎与会话管理。

使用 SQLAlchemy 2.0 async + asyncmy 驱动。提供：
- Base: 所有 ORM 模型的基类
- get_session: FastAPI 依赖，提供请求级会话
- init_db: 建表（用于开发/测试）
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """ORM 模型基类。"""


# 异步引擎：pool_recycle 避免 MySQL 8 的 wait_timeout 断连。
# 注意：不使用 pool_pre_ping —— asyncmy 0.2.10 与 SQLAlchemy 2.0 组合会因
# ping() 签名不兼容报错（TypeError: ping() missing 'reconnect'）。
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话，请求结束自动关闭。"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """建表（仅在测试/开发环境使用；生产建议用 Alembic 迁移）。"""
    # 延迟导入模型，确保注册到 Base.metadata
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)