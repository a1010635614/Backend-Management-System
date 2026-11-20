from contextlib import asynccontextmanager
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import admin, analytics, auth, posts, uploads
from app.core.config import get_settings
from app.core.database import engine, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    cache = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3,
                            socket_timeout=3, health_check_interval=30)
    web = httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False)
    app.state.redis, app.state.http = cache, web
    try:
        await cache.ping()
        yield
    finally:
        await web.aclose()
        await cache.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title='纸间博客 API', version='2.0.0', lifespan=lifespan,
                  description='异步博客、角色权限、Redis 认证与限流、私有 COS/CDN 附件及访问分析',
                  docs_url='/docs' if settings.docs_enabled else None, redoc_url=None,
                  openapi_url='/openapi.json' if settings.docs_enabled else None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(',')])
    app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(',')],
                       allow_credentials=False, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                       allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def request_metadata(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Request-ID'] = uuid.uuid4().hex
        if request.url.path.startswith(('/api/', '/docs', '/openapi.json')):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    @app.get('/api/health', tags=['运行状态'])
    async def health(request: Request, db: AsyncSession = Depends(get_db)):
        try:
            await db.execute(text('SELECT 1'))
            await request.app.state.redis.ping()
        except Exception:
            raise HTTPException(503, '依赖服务暂不可用') from None
        return {'status': 'UP', 'database': 'UP', 'redis': 'UP', 'version': '2.0.0'}

    @app.get('/api/public/config', tags=['博客'])
    async def public_config():
        return {'baiduId': get_settings().baidu_hm_id}

    for router in (auth.router, posts.router, admin.router, uploads.router, analytics.router):
        app.include_router(router)
    return app
