"""公共依赖：当前登录用户解析。"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError
from app.core.security import decode_access_token
from app.database import get_session
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 Bearer Token 解析当前用户；失败抛 401。"""
    if credentials is None:
        raise AuthError("缺少认证令牌")
    username = decode_access_token(credentials.credentials)
    if not username:
        raise AuthError("令牌无效或已过期")
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError("用户不存在")
    return user