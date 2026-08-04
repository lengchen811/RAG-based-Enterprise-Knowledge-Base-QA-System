"""认证路由：注册 / 登录。

统一响应格式：{code, message, data}，与其余接口保持一致。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import AppError
from app.core.responses import ok
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["认证"])


def _token_payload(user: User) -> dict:
    """构造统一格式的登录响应 data。"""
    return {
        "access_token": create_access_token(user.username),
        "token_type": "bearer",
        "user": UserOut.model_validate(user).model_dump(mode="json"),
    }


@router.post("/register")
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """注册新用户，成功即返回 Token。"""
    result = await session.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none() is not None:
        raise AppError("用户名已存在", code=409, status_code=409)

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return ok(_token_payload(user))


@router.post("/login")
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """登录：校验用户名密码，返回 Token。"""
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("用户名或密码错误", code=401, status_code=401)

    return ok(_token_payload(user))


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    """获取当前登录用户信息。"""
    return ok(UserOut.model_validate(user).model_dump(mode="json"))