"""RAG 全流程编排：检索 → 重排 → 拼装上下文 → 生成 → 引用溯源。

本模块是系统的"大脑"，将各子模块串成一条可观测的流水线，便于面试讲解与
Bad Case 排查。
"""
from __future__ import annotations

import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)

# 可选：启用 LangSmith 全链路追踪（在导入 langchain 前设置环境变量）
if settings.langsmith_enabled:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGCHAIN_API_KEY)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)
    logger.info("LangSmith 追踪已启用")


def retrieve_context(query: str, top_k: int = settings.RERANK_TOP_K) -> list[dict]:
    """执行混合检索 + 重排，返回命中的块（含 parent 上下文）。"""
    from app.services.rag.reranker import rerank
    from app.services.rag.retriever import HybridRetriever
    from app.services.rag.vectorstore import get_vector_store

    store = get_vector_store()
    if store.index is None or store.index.ntotal == 0:
        return []

    retriever = HybridRetriever(store)
    candidates = retriever.hybrid_search(query, top_k=settings.HYBRID_TOP_K)
    if not candidates:
        return []

    ordered = rerank(query, candidates, top_k=top_k)

    # 还原 parent 上下文
    results = []
    for rec in ordered:
        parent_text = store.get_parent_text(rec["parent_id"])
        results.append(
            {
                "document_id": rec.get("document_id"),
                "filename": rec.get("filename"),
                "child_index": rec.get("child_index"),
                "child_text": rec["text"],
                "parent_text": parent_text or rec["text"],
                "score": rec.get("fused_score") or rec.get("score"),
                "rerank_score": rec.get("rerank_score"),
            }
        )
    return results


def build_context(results: list[dict]) -> str:
    """将命中的 parent 上下文拼接为单一字符串供 Prompt 使用。"""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] 来源《{r['filename']}》\n{r['parent_text']}")
    return "\n\n".join(parts)


def build_sources(results: list[dict]) -> list[dict]:
    """构建前端可用的引用来源列表。"""
    return [
        {
            "document_id": r["document_id"],
            "filename": r["filename"],
            "chunk_index": r.get("child_index"),
            "score": round(float(r["score"]), 4) if r.get("score") is not None else None,
            "content_excerpt": (r["child_text"] or "")[:200],
        }
        for r in results
    ]


def build_prompt_with_history(
    question: str, context: str, history: list[dict]
) -> list:
    """构建 Prompt（含历史对话）。history 为 [{role, content}] 列表。"""
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
    )

    messages: list = [SystemMessage(content=build_system_prompt(context))]
    for m in history[-6:]:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            messages.append(AIMessage(content=m["content"]))
    messages.append(HumanMessage(content=question))
    return messages


def build_system_prompt(context: str) -> str:
    """构建系统提示词（含参考资料）。

    要点：强调"参考资料只针对当前问题"，历史对话仅用于理解指代，
    避免多轮对话中被历史话题带偏而误判"未找到"。
    """
    return (
        "你是企业知识库问答助手。请基于【参考资料】回答【当前问题】。\n"
        "要求：\n"
        "1. 每次回答只针对【当前问题】展开；【参考资料】是对应当前问题检索到的最新知识内容。\n"
        "2. 历史对话仅用于理解指代（如'它'、'那个'、'刚才说的'），不要被历史话题带偏。\n"
        "3. 若参考资料足以回答当前问题，请用简洁、结构化的中文作答，并尽量引用具体的章节或数据。\n"
        "4. 只有参考资料确实不足以回答当前问题，才回答'资料中未找到相关信息'，不要编造。\n"
        "5. 不要提及'参考资料'、'上下文'等内部措辞。\n"
        f"\n【参考资料】\n{context}"
    )


async def generate(messages: list) -> str:
    """调用大模型生成回答。"""
    from app.services.rag.llm import generate_answer

    return await generate_answer(messages)