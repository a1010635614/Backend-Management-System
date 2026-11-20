from datetime import datetime, timezone
from hashlib import sha256
import math

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, issue_token, permissions
from app.models import User
from app.schemas import EmailRequest, VerifyRequest
from app.services.auth import consume_code, reserve_and_send
from app.services.geetest import verify_challenge

router = APIRouter(prefix='/api/auth', tags=['认证'])


@router.get('/config')
async def config():
    settings = get_settings()
    return {'captchaId': settings.geetest_id, 'captchaRequired': settings.auth_captcha_required}


@router.post('/email/send', status_code=202)
async def send_email(body: EmailRequest, request: Request):
    cache = request.app.state.redis
    ip = request.client.host if request.client else 'unknown'
    await rate_limit(cache, 'send-ip:' + ip, 5, 600)
    settings = get_settings()
    await verify_challenge(request.app.state.http, body.geetest, settings)
    if settings.auth_captcha_required:
        key = 'blog:captcha-used:' + sha256(body.geetest['lot_number'].encode()).hexdigest()
        try:
            fresh = await cache.set(key, '1', nx=True, ex=600)
        except RedisError:
            raise HTTPException(503, '验证服务暂不可用') from None
        if not fresh:
            raise HTTPException(401, '行为验证已使用，请重新验证')
    await rate_limit(cache, 'send-email:' + body.email, 3, 1800)
    await reserve_and_send(cache, body.email, settings)
    return {'message': '验证码已发送', 'expiresIn': settings.email_code_ttl}


@router.post('/email/verify')
async def verify_email(body: VerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else 'unknown'
    await rate_limit(request.app.state.redis, 'verify-ip:' + ip, 20, 300)
    settings = get_settings()
    await consume_code(request.app.state.redis, body.email, body.code, settings)
    role = 'admin' if body.email in settings.administrators else 'viewer'
    await db.execute(insert(User).values(email=body.email, role=role).on_conflict_do_nothing(index_elements=[User.email]))
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not user.is_active:
        raise HTTPException(403, '账号不可用')
    if role == 'admin':
        user.role = 'admin'
    await db.commit()
    return {'access_token': issue_token(user), 'token_type': 'bearer',
            'expires_in': settings.jwt_exp_minutes * 60,
            'user': {'id': user.id, 'email': user.email, 'role': user.role, 'permissions': permissions(user)}}


@router.get('/me')
async def me(user: User = Depends(current_user)):
    return {'id': user.id, 'email': user.email, 'role': user.role, 'permissions': permissions(user)}


@router.post('/logout', status_code=204)
async def logout(request: Request, user: User = Depends(current_user)):
    claims = request.state.token_claims
    ttl = max(1, math.ceil(claims['exp'] - datetime.now(timezone.utc).timestamp()))
    try:
        await request.app.state.redis.set('blog:revoked:' + claims['jti'], '1', ex=ttl)
    except RedisError:
        raise HTTPException(503, '退出暂未完成，请重试') from None
    return Response(status_code=204)
