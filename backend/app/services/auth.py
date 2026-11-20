from hashlib import sha256
import hmac
import secrets

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.services.mail import send_code

RESERVE = '''
if redis.call('EXISTS',KEYS[1])==1 then return 0 end
redis.call('HSET',KEYS[1],'digest',ARGV[1],'owner',ARGV[2],'attempts',0,'status','pending')
redis.call('EXPIRE',KEYS[1],ARGV[3])
return 1
'''
FINISH = '''
if redis.call('HGET',KEYS[1],'owner')~=ARGV[1] then return 0 end
if ARGV[2]=='ready' then redis.call('HSET',KEYS[1],'status','ready') else redis.call('DEL',KEYS[1]) end
return 1
'''
CONSUME = '''
if redis.call('HGET',KEYS[1],'status')~='ready' then return 0 end
local attempts=tonumber(redis.call('HGET',KEYS[1],'attempts') or '0')
if attempts>=tonumber(ARGV[2]) then return -2 end
redis.call('HINCRBY',KEYS[1],'attempts',1)
if redis.call('HGET',KEYS[1],'digest')~=ARGV[1] then return -1 end
redis.call('DEL',KEYS[1])
return 1
'''


def code_key(email: str) -> str:
    return 'blog:code:' + sha256(email.encode()).hexdigest()


def code_digest(email: str, code: str, settings: Settings) -> str:
    return hmac.new(settings.jwt_secret.encode(), (email + ':' + code).encode(), sha256).hexdigest()


async def reserve_and_send(cache: Redis, email: str, settings: Settings) -> None:
    if not all((settings.mail_host, settings.mail_username, settings.mail_password)):
        raise HTTPException(503, '邮件服务尚未配置')
    code = f'{secrets.randbelow(1_000_000):06d}'
    owner = secrets.token_hex(16)
    key = code_key(email)
    try:
        reserved = await cache.eval(RESERVE, 1, key, code_digest(email, code, settings), owner, settings.email_code_ttl)
    except RedisError:
        raise HTTPException(503, '验证服务暂不可用') from None
    if not reserved:
        raise HTTPException(429, '验证码已发送，请稍后重试')
    try:
        await send_code(email, code, settings)
    except Exception:
        try:
            await cache.eval(FINISH, 1, key, owner, 'delete')
        except RedisError:
            pass
        raise HTTPException(502, '验证码邮件发送失败') from None
    try:
        ready = await cache.eval(FINISH, 1, key, owner, 'ready')
    except RedisError:
        raise HTTPException(503, '验证服务暂不可用，请稍后重试') from None
    if not ready:
        raise HTTPException(503, '验证码已过期，请重新发送')


async def consume_code(cache: Redis, email: str, code: str, settings: Settings) -> None:
    try:
        result = await cache.eval(CONSUME, 1, code_key(email), code_digest(email, code, settings), settings.email_code_attempts)
    except RedisError:
        raise HTTPException(503, '验证服务暂不可用') from None
    if result == -2:
        raise HTTPException(429, '验证码尝试次数已用尽')
    if result != 1:
        raise HTTPException(401, '验证码错误或已过期')
