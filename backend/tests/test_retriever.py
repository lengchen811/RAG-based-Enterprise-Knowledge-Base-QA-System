"""混合检索与向量存储测试。"""
import pytest

from app.services.rag.splitter import build_child_store, build_parent_lookup, split_markdown
from app.services.rag.vectorstore import VectorStore

SAMPLE = """# 员工手册

## 考勤制度
员工上下班需使用钉钉打卡，迟到超过30分钟算迟到。

## 休假制度
员工入职满一年后，每年享有5天带薪年假。
"""


@pytest.fixture()
def store(tmp_path):
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    children = build_child_store(parents)
    lookup = build_parent_lookup(parents)
    vs = VectorStore(tmp_path / "vs")
    vs.add_children(children, lookup)
    vs.save()
    return vs


def test_add_and_persist(store, tmp_path):
    vs = VectorStore(tmp_path / "vs")
    assert vs.load() is True
    assert vs.index is not None and vs.index.ntotal > 0


def test_hybrid_search_returns_results(store):
    from app.services.rag.retriever import HybridRetriever

    retriever = HybridRetriever(store)
    results = retriever.hybrid_search("年假有几天", top_k=5)
    assert len(results) > 0
    for r in results:
        assert "child_id" in r
        assert "parent_id" in r


def test_parent_context_restorable(store):
    from app.services.rag.retriever import HybridRetriever

    results = HybridRetriever(store).hybrid_search("年假", top_k=5)
    for r in results:
        parent = store.get_parent_text(r["parent_id"])
        assert parent is not None


def test_full_pipeline_without_rerank():
    """验证 pipeline 使用全局向量存储（模拟真实运行路径）。"""
    from app.services.rag import pipeline
    from app.services.rag.vectorstore import get_vector_store

    # 向全局存储写入数据
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    vs = get_vector_store()
    vs.add_children(build_child_store(parents), build_parent_lookup(parents))
    vs.save()

    context = pipeline.retrieve_context("年假有几天", top_k=2)
    assert len(context) > 0
    assert all("parent_text" in c for c in context)
    assert all("filename" in c for c in context)