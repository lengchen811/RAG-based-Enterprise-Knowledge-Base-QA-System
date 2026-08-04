"""应用配置：基于 pydantic-settings 从环境变量 / .env 读取。

所有配置项集中在此，便于统一管理、测试时覆盖。
"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/ 的上一级）
# 注意：config.py 位于 <root>/app/config.py，所以上一级是 <root>。
# 用 `.parent.parent`（而非 .parent.parent.parent），否则容器内 File(__file__) 为
# /app/app/config.py 时会向上算到 / 根目录，导致数据目录落在非共享卷上。
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """后端全局配置。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用 ----
    APP_NAME: str = "Enterprise RAG System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    # 允许跨域来源（前端地址）
    CORS_ORIGINS: List[str] = ["http://localhost:8501", "http://localhost:5173"]

    # ---- 数据库（异步）----
    DATABASE_URL: str = "mysql+asyncmy://rag:rag2024@localhost:3306/ragdb"

    # ---- Redis（Celery broker / result backend）----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- 认证 ----
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时

    # ---- 通义千问（DashScope）----
    DASHSCOPE_API_KEY: str = ""
    LLM_MODEL: str = "qwen-plus"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2048
    EMBEDDING_MODEL: str = "text-embedding-v3"
    RERANK_MODEL: str = "gte-rerank"

    # ---- RAG 检索参数 ----
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    CHILD_CHUNK_SIZE: int = 400
    CHILD_CHUNK_OVERLAP: int = 80
    HYBRID_TOP_K: int = 50   # 混合检索召回数
    RERANK_TOP_K: int = 5    # 重排后送入大模型的块数
    VECTOR_WEIGHT: float = 0.5   # 向量召回权重（混合打分）
    BM25_WEIGHT: float = 0.5     # BM25 召回权重
    FAISS_INDEX_FILE: str = "faiss.index"
    FAISS_PK_FILE: str = "faiss.pkl"

    # ---- 文件存储 ----
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    VECTOR_DIR: Path = BASE_DIR / "data" / "vectorstore"
    MAX_UPLOAD_SIZE_MB: int = 20
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "md", "txt"]

    # ---- 可观测性（可选，无 Key 自动跳过）----
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "enterprise-rag"

    @property
    def langsmith_enabled(self) -> bool:
        """LangSmith 是否启用：显式开启且提供 Key。"""
        return self.LANGCHAIN_TRACING_V2 and bool(self.LANGCHAIN_API_KEY)


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免重复解析环境变量。"""
    return Settings()


settings = get_settings()