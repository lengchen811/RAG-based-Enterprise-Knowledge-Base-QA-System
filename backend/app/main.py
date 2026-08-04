"""FastAPI 应用入口。

启动方式：
    uvicorn app.main:app --host 0.0.0.0 --port 8000

生命周期：启动时建表（开发用），并派发一次性的索引初始化任务。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.responses import ok


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时初始化数据库表（开发环境；生产建议 Alembic）
    from app.database import init_db

    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
register_exception_handlers(app)

# 路由
app.include_router(api_router)


@app.get("/health", tags=["系统"])
async def health() -> dict:
    """健康检查。"""
    return ok({"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION})


@app.get("/", tags=["系统"])
async def root() -> dict:
    return ok({"message": "Enterprise RAG System API", "docs": "/docs"})