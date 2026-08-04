"""FAISS 向量存储（本地持久化）。

设计：
- Child 块向量化后加入 FAISS，index 与 `records`（元数据列表）按下标对齐。
- 向量归一化后使用内积（等价余弦相似度）。
- 维护 `parent_lookup`（parent_id -> parent_text），用于检索后还原上下文。
- 通过 `save` / `load` 持久化到磁盘（共享卷），供 API 与 Worker 复用。

说明：单机部署下，为保证索引一致，本项目采用单 API + 单 Worker，索引写入
共享卷。生产多副本场景应改用 Milvus/向量数据库（见 README 演进建议）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import faiss
import numpy as np

from app.config import settings


class VectorStore:
    """基于 FAISS 的向量检索封装。"""

    def __init__(self, index_dir: str | Path | None = None):
        self.index_dir = Path(index_dir or settings.VECTOR_DIR)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.dim: int | None = None
        self.index: faiss.Index | None = None
        self.records: list[dict] = []          # 与 index 下标对齐的元数据
        self.parent_lookup: dict[str, str] = {}  # parent_id -> parent_text
        self._last_fp: tuple | None = None     # 索引文件指纹，用于检测 worker 更新

    # ---------- 初始化 / 持久化 ----------

    def _ensure_index(self, dim: int) -> None:
        """按需创建扁平内积索引。"""
        if self.index is None or self.dim != dim:
            self.dim = dim
            self.index = faiss.IndexFlatIP(dim)

    def save(self) -> None:
        """将索引与元数据持久化到磁盘。"""
        if self.index is None:
            return
        faiss.write_index(self.index, str(self.index_dir / settings.FAISS_INDEX_FILE))
        with (self.index_dir / settings.FAISS_PK_FILE).open("w", encoding="utf-8") as f:
            json.dump(
                {"records": self.records, "parent_lookup": self.parent_lookup},
                f,
                ensure_ascii=False,
            )

    def load(self) -> bool:
        """从磁盘加载索引；不存在则返回 False。"""
        idx_file = self.index_dir / settings.FAISS_INDEX_FILE
        pk_file = self.index_dir / settings.FAISS_PK_FILE
        if not (idx_file.exists() and pk_file.exists()):
            return False
        self.index = faiss.read_index(str(idx_file))
        self.dim = self.index.d
        with pk_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.records = data.get("records", [])
        self.parent_lookup = data.get("parent_lookup", {})
        self._last_fp = self._file_fingerprint(idx_file)
        return True

    @staticmethod
    def _file_fingerprint(idx_file: Path) -> tuple:
        """索引文件的 (mtime, size) 指纹，用于检测是否被 worker 更新。"""
        try:
            st = idx_file.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def reload_if_changed(self) -> bool:
        """若索引文件已被其他进程（worker）更新，则重新加载。

        返回是否发生了重新加载。用于解决"API 单例缓存旧索引、看不到新文档"的问题。
        """
        idx_file = self.index_dir / settings.FAISS_INDEX_FILE
        if not idx_file.exists():
            return False
        fp = self._file_fingerprint(idx_file)
        if fp is not None and fp != getattr(self, "_last_fp", None):
            self.load()
            return True
        return False

    # ---------- 写入 ----------

    def add_children(self, children: list, parent_lookup: dict[str, str]) -> int:
        """批量向量化并加入 Child 块。

        Args:
            children: list[ChildChunk]
            parent_lookup: parent_id -> parent_text 映射

        Returns:
            新增的向量数量。
        """
        if not children:
            return 0
        texts = [c.text for c in children]
        from app.services.rag.embeddings import embed_texts

        vectors = embed_texts(texts)
        if not vectors:
            return 0

        dim = len(vectors[0])
        self._ensure_index(dim)
        arr = np.array(vectors, dtype="float32")
        self._normalize(arr)
        base = self.index.ntotal
        self.index.add(arr)
        for i, c in enumerate(children):
            self.records.append(
                {
                    "child_id": c.child_id,
                    "text": c.text,
                    "parent_id": c.parent_id,
                    **c.metadata,
                }
            )
        self.parent_lookup.update(parent_lookup)
        return len(vectors)

    def delete_document(self, document_id: int) -> None:
        """删除指定文档的所有向量（重建索引）。"""
        keep = [r for r in self.records if r.get("document_id") != document_id]
        if len(keep) == len(self.records):
            return
        # 重建索引
        if self.index is not None and keep:
            texts = [r["text"] for r in keep]
            from app.services.rag.embeddings import embed_texts

            vectors = embed_texts(texts)
            dim = len(vectors[0])
            new_index = faiss.IndexFlatIP(dim)
            arr = np.array(vectors, dtype="float32")
            self._normalize(arr)
            new_index.add(arr)
            self.index = new_index
            self.dim = dim
        else:
            self.index = None
            self.dim = None
        self.records = keep

    # ---------- 检索 ----------

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """向量检索，返回块及元数据（含 parent_id）。"""
        if self.index is None or self.index.ntotal == 0:
            return []
        from app.services.rag.embeddings import embed_query

        qvec = np.array([embed_query(query)], dtype="float32")
        self._normalize(qvec)
        scores, ids = self.index.search(qvec, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            rec = self.records[int(idx)].copy()
            rec["score"] = float(score)
            results.append(rec)
        return results

    def get_parent_text(self, parent_id: str) -> str | None:
        """根据 parent_id 还原父级上下文。"""
        return self.parent_lookup.get(parent_id)

    @staticmethod
    def _normalize(arr: np.ndarray) -> None:
        """就地 L2 归一化，使内积等于余弦相似度。"""
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr /= norms


# 全局单例（进程内共享）
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """获取全局向量存储实例（惰性加载，且检测 worker 更新后自动重载）。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
        _vector_store.load()
    else:
        # worker 可能已向索引写入新文档，检测到文件变化则重新加载
        _vector_store.reload_if_changed()
    return _vector_store