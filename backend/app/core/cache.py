from hashlib import sha256

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError


def get_cache(request: Request) -> Redis:
    return request.app.state.redis


async def rate_limit(cache: Redis, identity: str, limit: int, seconds: int) -> None:
    # INCR + expiry must be atomic; an interrupted client cannot leave an immortal key.
    script = '''
    local count=redis.call('INCR',KEYS[1])
    if count==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end
    return {count,redis.call('TTL',KEYS[1])}
    '''
    key = 'blog:limit:' + sha256(identity.encode()).hexdigest()
    try:
        count, remaining = await cache.eval(script, 1, key, seconds)
    except RedisError:
        raise HTTPException(503, '验证服务暂不可用') from None
    if count > limit:
        raise HTTPException(429, '请求过于频繁，请稍后重试', headers={'Retry-After': str(max(1, remaining))})
