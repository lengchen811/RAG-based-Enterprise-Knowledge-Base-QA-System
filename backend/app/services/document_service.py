"""文档服务：上传落盘相关辅助。"""
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.core.exceptions import AppError


async def save_upload_file(user_id: int, file: UploadFile) -> Path:
    """将上传文件落盘到用户专属目录，并校验大小。

    返回最终文件路径。
    """
    # 用户目录：data/uploads/{user_id}/
    user_dir = settings.UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名，避免冲突与路径穿越
    ext = Path(file.filename or "").suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = user_dir / unique_name

    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise AppError(f"文件超过大小限制（{settings.MAX_UPLOAD_SIZE_MB}MB）")
            f.write(chunk)

    return dest