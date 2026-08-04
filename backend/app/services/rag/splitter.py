"""语义切分与父子文档策略 (Parent-Child Retriever)。

设计思路：
1. **Parent 层**：用 `MarkdownHeaderTextSplitter` 按文档标题层级切分，保证每个
   Parent 都是一个完整的语义知识块（章节/小节），保留上下文。
2. **Child 层**：对每个 Parent 再用 `RecursiveCharacterTextSplitter` 切成小块，
   Child 用于向量化检索（更精准），检索命中 Child 后取回其 Parent 喂给大模型
   （上下文更完整）。兼顾"召回精准度"与"生成上下文丰富度"。

存储结构：
- Child 向量化存入 FAISS，并记录其 parent_id。
- 单独维护 parent_id -> parent_text 的映射，供检索后还原上下文。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.config import settings


@dataclass
class ChildChunk:
    """向量化检索的最小单元。"""

    child_id: str
    text: str
    parent_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParentChunk:
    """语义上下文单元，喂给大模型。"""

    parent_id: str
    parent_text: str
    metadata: dict = field(default_factory=dict)
    children: list[ChildChunk] = field(default_factory=list)


def _stable_id(text: str) -> str:
    """基于内容的稳定哈希 ID。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def split_markdown(markdown_text: str, document_id: int, filename: str) -> list[ParentChunk]:
    """将 Markdown 文档切分为父子文档结构。

    Args:
        markdown_text: 结构化 Markdown 文本。
        document_id: 文档 ID，写入元数据用于溯源。
        filename: 文档名，写入元数据用于引用展示。

    Returns:
        list[ParentChunk]：每个包含标题语义的 Parent 及其 Child 块。
    """
    # ---- 1. Parent 层：按标题层级切分 ----
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    header_docs = header_splitter.split_text(markdown_text)

    # 若没有识别到任何标题（header_docs 为空或仅一个），退化为递归切分
    if not header_docs:
        fallback = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )
        header_docs = fallback.split_text(markdown_text)

    # ---- 2. Child 层：对每个 Parent 再切分 ----
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHILD_CHUNK_SIZE,
        chunk_overlap=settings.CHILD_CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )

    parents: list[ParentChunk] = []
    for i, hdoc in enumerate(header_docs):
        parent_text = hdoc.page_content.strip()
        if not parent_text:
            continue
        parent_id = _stable_id(parent_text)
        parent_meta = {
            "document_id": document_id,
            "filename": filename,
            "parent_index": i,
            "header_meta": hdoc.metadata,
        }

        # 子块切分
        child_texts = child_splitter.split_text(parent_text)
        children: list[ChildChunk] = []
        for j, ct in enumerate(child_texts):
            ct = ct.strip()
            if not ct:
                continue
            children.append(
                ChildChunk(
                    child_id=_stable_id(ct),
                    text=ct,
                    parent_id=parent_id,
                    metadata={
                        "document_id": document_id,
                        "filename": filename,
                        "parent_index": i,
                        "child_index": j,
                        "header_meta": hdoc.metadata,
                    },
                )
            )

        if children:
            parents.append(
                ParentChunk(
                    parent_id=parent_id,
                    parent_text=parent_text,
                    metadata=parent_meta,
                    children=children,
                )
            )

    return parents


def build_parent_lookup(parents: list[ParentChunk]) -> dict[str, str]:
    """构建 parent_id -> parent_text 的映射，用于检索后还原上下文。"""
    return {p.parent_id: p.parent_text for p in parents}


def build_child_store(parents: list[ParentChunk]) -> list[ChildChunk]:
    """摊平所有 Child 块，供向量化入库。"""
    return [c for p in parents for c in p.children]