"""文档处理任务：解析 → 切分 → 向量化 → 更新状态机。

在 Celery Worker 中异步执行，避免阻塞 API 主线程。
状态流转：PENDING -> PROCESSING -> COMPLETED / FAILED
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.services.rag.parser import parse_document
from app.services.rag.splitter import build_child_store, build_parent_lookup, split_markdown
from app.services.rag.vectorstore import get_vector_store
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process(document_id: int) -> None:
    """异步处理单个文档。"""
    # 释放连接池：Celery 每任务 asyncio.run() 新建事件循环，若不释放旧循环的连接，
    # 会报 "Future attached to a different loop"。
    from app.database import engine

    await engine.dispose()

    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            logger.warning("文档 %s 不存在，跳过", document_id)
            return

        # 标记 PROCESSING
        doc.status = DocumentStatus.PROCESSING
        await session.commit()

        try:
            # 1. 结构化解析
            markdown = parse_document(doc.file_path)

            # 2. 语义切分（父子文档）
            parents = split_markdown(markdown, document_id=doc.id, filename=doc.filename)
            if not parents:
                raise ValueError("未能从文档中提取出任何内容")

            # 3. 向量化入库
            children = build_child_store(parents)
            parent_lookup = build_parent_lookup(parents)
            store = get_vector_store()
            added = store.add_children(children, parent_lookup)
            store.save()

            # 4. 更新状态
            doc.status = DocumentStatus.COMPLETED
            doc.chunk_count = added
            doc.error_msg = None
            await session.commit()
            logger.info("文档 %s 处理完成，共 %s 个向量块", document_id, added)

        except Exception as exc:  # noqa: BLE001
            logger.exception("文档 %s 处理失败", document_id)
            doc.status = DocumentStatus.FAILED
            doc.error_msg = str(exc)[:2000]
            await session.commit()


@celery_app.task(name="document.process_document", bind=True, max_retries=2)
def process_document_task(self, document_id: int) -> None:
    """Celery 任务入口：在 Worker 中运行异步处理。"""
    try:
        asyncio.run(_process(document_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("文档 %s 任务异常", document_id)
        raise self.retry(exc=exc, countdown=5) from exc