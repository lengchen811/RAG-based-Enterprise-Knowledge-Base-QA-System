"""混合检索：向量召回 + BM25 关键词召回，取并集融合。

痛点：单一向量检索对"专有名词"（工号、产品型号）不敏感；纯关键词检索对同义
表达失效。混合双路召回 + 加权融合，兼顾语义与关键词。

融合策略：以 child_id 为统一去重键，对两路召回结果做线性加权求和，去重取 top_k。
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.config import settings
from app.services.rag.vectorstore import VectorStore


def tokenize(text: str) -> list[str]:
    """轻量中文/英文分词：英文整词 + 中文单字 + 数字。

    说明：为避免引入 jieba 等重依赖，采用"英文单词 + 中文单字"的朴素分词，
    对 RAG 检索已足够。需要更优分词效果可替换为 jieba。
    """
    return [m.group(0).lower() for m in re.finditer(r"[a-zA-Z0-9_]+|[一-鿿]", text)]


class HybridRetriever:
    """向量 + BM25 双路召回，融合去重。"""

    def __init__(
        self,
        vector_store: VectorStore,
        top_k: int = settings.HYBRID_TOP_K,
        vector_weight: float = settings.VECTOR_WEIGHT,
        bm25_weight: float = settings.BM25_WEIGHT,
    ):
        self.store = vector_store
        self.top_k = top_k
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self._bm25: BM25Okapi | None = None
        self._bm25_fingerprint: tuple | None = None

    # ---------- BM25 索引 ----------

    def _get_bm25(self) -> BM25Okapi | None:
        """构建 BM25 索引；当语料变化时自动重建。"""
        texts = [r["text"] for r in self.store.records]
        if not texts:
            return None
        fp = (len(texts), self.store.records[-1]["child_id"] if self.store.records else None)
        if self._bm25 is None or self._bm25_fingerprint != fp:
            self._bm25 = BM25Okapi([tokenize(t) for t in texts])
            self._bm25_fingerprint = fp
        return self._bm25

    def hybrid_search(self, query: str, top_k: int | None = None) -> list[dict]:
        """双路召回后融合，返回按相关性排序的块列表（含 parent_id）。"""
        k = top_k or self.top_k
        fused: dict[str, float] = {}      # child_id -> 融合分数
        meta: dict[str, dict] = {}        # child_id -> 记录

        # 1. 向量召回
        for r in self.store.search(query, top_k=k):
            cid = r["child_id"]
            fused[cid] = fused.get(cid, 0.0) + self.vector_weight * r["score"]
            meta[cid] = r

        # 2. BM25 召回
        bm25 = self._get_bm25()
        if bm25 is not None:
            bm_scores = bm25.get_scores(tokenize(query))
            top_idx = sorted(
                range(len(bm_scores)), key=lambda i: bm_scores[i], reverse=True
            )[:k]
            if top_idx and bm_scores[top_idx[0]] > 0:
                max_bm = bm_scores[top_idx[0]]
                for idx in top_idx:
                    if bm_scores[idx] <= 0:
                        continue
                    rec = self.store.records[idx]
                    cid = rec["child_id"]
                    norm = bm_scores[idx] / (max_bm + 1e-9)
                    fused[cid] = fused.get(cid, 0.0) + self.bm25_weight * norm
                    meta.setdefault(cid, {**rec, "score": 0.0})

        # 3. 融合分数排序取 top_k
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [{**meta[cid], "fused_score": score} for cid, score in ranked]