"""pytest 共享配置与夹具。

- 使用 SQLite（内存/临时文件）替代 MySQL，避免依赖外部服务。
- 用确定性伪嵌入替换真实 DashScope API，使测试可离线运行。
"""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

# 确保可以 import app 包
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 必须在导入 app 前设置测试环境变量
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_rag.db"
os.environ["VECTOR_DIR"] = str(BACKEND_DIR / "data" / "test_vectorstore")
os.environ["UPLOAD_DIR"] = str(BACKEND_DIR / "data" / "test_uploads")
os.environ["JWT_SECRET"] = "test-secret"
os.environ["DASHSCOPE_API_KEY"] = "test-key"


@pytest.fixture(scope="session", autouse=True)
def mock_embeddings():
    """用确定性伪嵌入替换真实 Embedding API（session 级，覆盖所有测试）。"""
    import app.services.rag.embeddings as emb

    def fake_texts(texts):
        return [
            np.random.default_rng(abs(hash(t)) % 2**32).normal(size=64).tolist()
            for t in texts
        ]

    def fake_query(q):
        return np.random.default_rng(abs(hash(q)) % 2**32).normal(size=64).tolist()

    emb.embed_texts = fake_texts
    emb.embed_query = fake_query
    yield


@pytest.fixture()
def mock_llm(monkeypatch):
    """用假 LLM 替换真实通义千问。"""
    from langchain_core.messages import AIMessage, AIMessageChunk

    import app.services.rag.llm as llm

    class FakeLLM:
        async def astream(self, messages):
            for t in ["你好", "，", "这是", "测试", "回答。"]:
                yield AIMessageChunk(content=t)

        async def ainvoke(self, messages):
            return AIMessage(content="这是测试回答。")

    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM())

    async def fake_generate(messages):
        # 与生产 generate_answer 一致：返回字符串
        return (await FakeLLM().ainvoke(messages)).content

    monkeypatch.setattr(llm, "generate_answer", fake_generate)


@pytest.fixture(scope="session", autouse=True)
def mock_celery():
    """测试环境无 Redis，mock 掉 Celery 派发，避免超时回退。"""
    from app.tasks.celery_app import celery_app

    celery_app.send_task = lambda *a, **k: None


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    """清理测试产物。"""
    yield
    for f in ["test_rag.db"]:
        p = Path(BACKEND_DIR) / f
        if p.exists():
            p.unlink(missing_ok=True)