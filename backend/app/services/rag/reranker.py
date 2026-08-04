"""重排序：Cross-Encoder 二次精排。

对混合检索召回的 Top-k 候选块，用 Qwen Rerank（gte-rerank）按"查询-块"相关性
二次打分，截取 Top-N 送入大模型。解决 RAG 的"最后一公里"问题，降低幻觉。

容错：若 Rerank API 不可用/超时，回退到"保留原召回顺序"，保证主流程可用。
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = settings.RERANK_TOP_K,
) -> list[dict]:
    """对候选块重排，返回按相关性降序的 top_k 个块。"""
    if not candidates:
        return []
    if len(candidates) <= 1:
        return candidates[:top_k]

    try:
        return _dashscope_rerank(query, candidates, top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rerank API 不可用，回退到原召回顺序: %s", exc)
        # 回退：按 fused_score 排序（混合检索已给出）
        ordered = sorted(candidates, key=lambda c: c.get("fused_score", 0.0), reverse=True)
        return ordered[:top_k]


def _dashscope_rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """调用 DashScope gte-rerank 进行精排。"""
    import dashscope

    documents = [c["text"] for c in candidates]
    resp = dashscope.TextReRank.call(
        model=settings.RERANK_MODEL,
        query=query,
        documents=documents,
        top_n=top_k,
        api_key=settings.DASHSCOPE_API_KEY,
    )
    if resp is None or resp.status_code != 200:
        raise RuntimeError(f"Rerank API 返回异常: {getattr(resp, 'status_code', 'unknown')}")

    results = resp.output.results if hasattr(resp, "output") else []
    ordered: list[dict] = []
    for item in results:
        idx = item.index
        if 0 <= idx < len(candidates):
            rec = dict(candidates[idx])
            rec["rerank_score"] = item.relevance_score
            ordered.append(rec)
    # 保底：若一轮结果不足 top_k，补上未命中的候选
    if len(ordered) < top_k:
        seen = {r["child_id"] for r in ordered}
        for c in candidates:
            if c["child_id"] not in seen:
                ordered.append(c)
                seen.add(c["child_id"])
            if len(ordered) >= top_k:
                break
    return ordered[:top_k]