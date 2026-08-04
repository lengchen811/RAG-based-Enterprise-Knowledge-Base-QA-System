"""统一 API 响应格式。

约定：{ "code": 0, "message": "ok", "data": ... }
code=0 表示成功，非 0 表示业务错误。
"""
from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None, message: str = "ok") -> JSONResponse:
    """成功响应。"""
    return JSONResponse({"code": 0, "message": message, "data": data})


def fail(message: str, code: int = 400, status_code: int = 400, detail: Any = None) -> JSONResponse:
    """失败响应。"""
    body: dict[str, Any] = {"code": code, "message": message, "data": None}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)