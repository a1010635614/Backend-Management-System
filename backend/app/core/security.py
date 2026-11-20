from datetime import datetime, timedelta, timezone
import secrets

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)
PERMISSIONS = {
    'admin': {'posts:read', 'posts:write', 'posts:delete', 'uploads:write', 'analytics:read', 'users:manage'},
    'editor': {'posts:read', 'posts:write', 'posts:delete', 'uploads:write', 'analytics:read'},
    'viewer': set(),
}


def permissions(user: User) -> list[str]:
    return sorted(PERMISSIONS.get(user.role, set()))


def issue_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user.id), 'jti': secrets.token_hex(24), 'iat': now,
                       'exp': now + timedelta(minutes=settings.jwt_exp_minutes),
                       'iss': settings.jwt_issuer}, settings.jwt_secret, algorithm='HS256')


async def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                       db: AsyncSession = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(401, '请先登录', headers={'WWW-Authenticate': 'Bearer'})
    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=['HS256'],
                             issuer=settings.jwt_issuer, options={'require': ['exp', 'iat', 'sub', 'jti', 'iss']})
        user_id = int(payload['sub'])
        if not isinstance(payload['jti'], str) or len(payload['jti']) != 48:
            raise ValueError('Invalid token identifier')
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, '登录已失效') from None
    try:
        if await request.app.state.redis.exists('blog:revoked:' + payload['jti']):
            raise HTTPException(401, '登录已退出')
    except RedisError:
        raise HTTPException(503, '会话验证暂不可用') from None
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(401, '账号不可用')
    request.state.token_claims = payload
    return user


def require(permission: str):
    async def check(user: User = Depends(current_user)) -> User:
        if permission not in permissions(user):
            raise HTTPException(403, '没有执行此操作的权限')
        return user
    return check
