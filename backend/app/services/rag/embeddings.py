"""嵌入模型：基于 DashScope 的文本向量化。

通过模型工厂抽象，默认使用通义 `text-embedding-v3`，可替换为其他 Embedding。
"""
from functools import lru_cache

from langchain_community.embeddings import DashScopeEmbeddings

from app.config import settings


@lru_cache
def get_embeddings() -> DashScopeEmbeddings:
    """返回缓存的嵌入模型实例（单例，避免重复初始化）。"""
    return DashScopeEmbeddings(
        model=settings.EMBEDDING_MODEL,
        dashscope_api_key=settings.DASHSCOPE_API_KEY,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化文本。"""
    return get_embeddings().embed_documents(texts)


def embed_query(query: str) -> list[float]:
    """向量化查询。"""
    return get_embeddings().embed_query(query)