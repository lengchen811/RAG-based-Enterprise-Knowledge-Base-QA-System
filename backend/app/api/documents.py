"""文档管理路由：上传、列表、状态查询、删除。

统一响应格式：{code, message, data}。
"""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.responses import ok
from app.database import get_session
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentOut
from app.services.document_service import save_upload_file
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/documents", tags=["文档"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """上传文档：落盘并创建状态为 PENDING 的记录，随后异步派发处理任务。"""
    # 1. 格式校验
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise AppError(f"不支持的文件类型: {ext}，仅支持 {settings.ALLOWED_EXTENSIONS}")

    # 2. 落盘（限制大小）
    file_path = await save_upload_file(user.id, file)

    # 3. 创建 PENDING 记录
    doc = Document(
        user_id=user.id,
        filename=file.filename,
        file_path=str(file_path),
        file_size=os.path.getsize(file_path),
        status=DocumentStatus.PENDING,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    # 4. 异步派发处理任务（Celery）；Woker 不可用时降级为 PENDING，可后续重试
    try:
        celery_app.send_task("document.process_document", args=[doc.id])
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "派发文档处理任务失败（doc=%s）: %s", doc.id, exc
        )

    return ok(DocumentOut.model_validate(doc).model_dump(mode="json"))


@router.get("")
async def list_documents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """列出当前用户的文档。"""
    result = await session.execute(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    items = result.scalars().all()
    return ok(
        {
            "total": len(items),
            "items": [DocumentOut.model_validate(d).model_dump(mode="json") for d in items],
        }
    )


@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """查询单个文档及其处理状态。"""
    doc = await session.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise NotFoundError("文档不存在")
    return ok(DocumentOut.model_validate(doc).model_dump(mode="json"))


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除文档及其本地文件。"""
    doc = await session.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise NotFoundError("文档不存在")
    # 清理本地文件
    try:
        p = Path(doc.file_path)
        if p.exists() and p.is_file():
            p.unlink()
    except OSError:
        pass
    await session.delete(doc)
    await session.commit()
    return ok({"deleted": True, "id": doc_id})