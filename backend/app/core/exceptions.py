"""统一业务异常与全局异常处理器。

设计：应用层抛出 `AppError`（带 code + message），由全局处理器转换为统一响应格式。
未处理的异常会被记录到日志（便于排查），但生产环境不向客户端泄露内部细节。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import fail

logger = logging.getLogger(__name__)


class AppError(Exception):
    """业务异常基类。"""

    def __init__(self, message: str, code: int = 400, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=404, status_code=404)


class AuthError(AppError):
    def __init__(self, message: str = "未认证或凭证无效"):
        super().__init__(message, code=401, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "无权限访问"):
        super().__init__(message, code=403, status_code=403)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用。"""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return fail(exc.message, code=exc.code, status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return fail(str(exc.detail), code=exc.status_code, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return fail("请求参数校验失败", code=422, status_code=422, detail=exc.errors())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        # 记录完整堆栈到日志，便于排查（生产也需留痕）
        logger.exception("未处理的异常: %s", exc)
        # 生产环境不向客户端泄露内部细节
        msg = "服务器内部错误" if not app.debug else str(exc)
        return fail(msg, code=500, status_code=500)