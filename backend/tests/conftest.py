import asyncio
import os
import re
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from sqlalchemy import text

# Even collection without an integration harness cannot use local production credentials.
os.environ.update({
    'APP_ENV': 'test',
    'DATABASE_URL': os.getenv('TEST_DATABASE_URL', 'postgresql+asyncpg://test:test@127.0.0.1:1/blogtest'),
    'REDIS_URL': os.getenv('TEST_REDIS_URL', 'redis://127.0.0.1:1/15'),
    'JWT_SECRET': 'test-only-isolated-signing-key-with-48-characters',
    'ADMIN_EMAILS': 'admin@example.com', 'ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
    'MAIL_HOST': 'smtp.example.com', 'MAIL_USERNAME': 'noreply@example.com', 'MAIL_PASSWORD': 'test-only',
    'MAIL_FROM': 'noreply@example.com', 'MAIL_PORT': '465',
    'GEETEST_ID': 'fixture-captcha-id', 'GEETEST_KEY': 'fixture-captcha-key',
    'AUTH_CAPTCHA_REQUIRED': 'true', 'GEETEST_VERIFY_URL': 'https://gcaptcha4.geetest.com/validate',
    'COS_SECRET_ID': 'test-only', 'COS_SECRET_KEY': 'test-only', 'COS_BUCKET': 'test-123',
    'CDN_BASE_URL': 'https://cdn.example.com', 'CDN_AUTH_KEY': 'ExampleKey123',
})

from app.application import create_app
from app.core.database import SessionLocal, engine
from app.core.security import issue_token
from app.models import User
from app.services import auth as auth_service, storage


class BoundedClient(httpx.AsyncClient):
    async def request(self, *args, **kwargs):
        # ASGITransport has no network timeout. Bound an application deadlock too.
        async with asyncio.timeout(15):
            return await super().request(*args, **kwargs)


@pytest.fixture(scope='session')
def isolated():
    if os.getenv('BLOG_TEST_ISOLATED') != '1' or not os.getenv('TEST_DATABASE_URL') or not os.getenv('TEST_REDIS_URL'):
        pytest.skip('Requires the disposable PostgreSQL + Redis harness; no production fallback')
    assert re.fullmatch(r'postgresql\+asyncpg://blog_test@127\.0\.0\.1:[0-9]+/blogtest', os.environ['TEST_DATABASE_URL'])
    match = re.fullmatch(r'redis://127\.0\.0\.1:([0-9]+)/15', os.environ['TEST_REDIS_URL'])
    assert match and int(match[1]) > 1024 and int(match[1]) != 6379


@pytest_asyncio.fixture
async def client(isolated, monkeypatch):
    async with asyncio.timeout(15):
        async with engine.begin() as connection:
            await connection.execute(text('TRUNCATE assets, posts, analytics_events, email_codes, users RESTART IDENTITY CASCADE'))
    state = {'mail': {}, 'mail_calls': 0, 'verify_result': 'success', 'metadata': {'Content-Length': '12', 'Content-Type': 'image/png'}, 'cos_calls': []}

    async def send(email, code, settings):
        state['mail_calls'] += 1
        await asyncio.sleep(.02)
        state['mail'][email] = code
    monkeypatch.setattr(auth_service, 'send_code', send)

    class Cos:
        def get_presigned_url(self, **kwargs):
            state['cos_calls'].append(kwargs)
            return 'https://storage.example.com/' + kwargs['Key'] + '?test-signature=fixture'
        def head_object(self, **kwargs):
            return state['metadata']
    monkeypatch.setattr(storage, 'cos_client', lambda: Cos())

    def provider(request):
        state['provider_request'] = request
        return httpx.Response(200, json={'result': state['verify_result']})

    app = create_app()
    async with LifespanManager(app):
        await app.state.redis.flushdb()
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider), trust_env=False) as external:
            app.state.http = external
            async with BoundedClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as web:
                web.fixture_state = state
                web.fixture_app = app
                yield web


@pytest_asyncio.fixture
async def identities(client):
    async with SessionLocal() as db:
        admin = User(email='admin@example.com', role='admin')
        editor = User(email='editor@example.com', role='editor')
        other = User(email='other@example.com', role='editor')
        viewer = User(email='reader@example.com', role='viewer')
        db.add_all([admin, editor, other, viewer]); await db.commit()
        return {user.role if user.email != 'other@example.com' else 'other': {
                    'id': user.id, 'email': user.email, 'headers': {'Authorization': 'Bearer ' + issue_token(user)}}
                for user in (admin, editor, other, viewer)}


def proof():
    return {'lot_number': uuid4().hex, 'captcha_output': 'fixture-output', 'pass_token': 'fixture-pass', 'gen_time': '1700000000'}
