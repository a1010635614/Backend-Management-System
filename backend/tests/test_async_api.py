import asyncio
from datetime import datetime, timedelta, timezone
import hmac
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Asset, User
from app.services.auth import code_key
from conftest import proof


async def send(client, email='reader@example.com', challenge=None):
    return await client.post('/api/auth/email/send', json={'email': email, 'geetest': challenge or proof()})


async def login(client, email='reader@example.com'):
    assert (await send(client, email)).status_code == 202
    return await client.post('/api/auth/email/verify', json={'email': email, 'code': client.fixture_state['mail'][email]})


async def test_real_postgresql_redis_health_and_swagger(client):
    assert (await client.get('/api/health')).json()['redis'] == 'UP'
    assert (await client.get('/docs')).status_code == 200
    spec = (await client.get('/openapi.json')).json()
    assert spec['info']['version'] == '2.0.0'
    assert spec['paths']['/api/admin/posts']['post']['security']


async def test_captcha_missing_invalid_and_replayed_are_rejected(client):
    assert (await client.post('/api/auth/email/send', json={'email': 'reader@example.com'})).status_code == 400
    client.fixture_state['verify_result'] = 'fail'
    assert (await send(client)).status_code == 401
    assert client.fixture_state['mail_calls'] == 0
    client.fixture_state['verify_result'] = 'success'
    challenge = proof()
    assert (await send(client, challenge=challenge)).status_code == 202
    assert (await send(client, email='other@example.com', challenge=challenge)).status_code == 401
    request = client.fixture_state['provider_request']
    form = parse_qs(request.content.decode())
    expected = hmac.new(get_settings().geetest_key.encode(), challenge['lot_number'].encode(), sha256).hexdigest()
    assert form['sign_token'] == [expected]


async def test_redis_code_is_hashed_expiring_and_single_use(client):
    assert (await send(client, 'READER@example.com')).status_code == 202
    key = code_key('reader@example.com')
    cache = client.fixture_app.state.redis
    stored = await cache.hgetall(key)
    assert client.fixture_state['mail']['reader@example.com'] not in stored.values()
    assert 0 < await cache.ttl(key) <= 300
    body = {'email': 'reader@example.com', 'code': client.fixture_state['mail']['reader@example.com']}
    first = await client.post('/api/auth/email/verify', json=body)
    assert first.status_code == 200
    assert first.json()['user']['role'] == 'viewer'
    assert (await client.post('/api/auth/email/verify', json=body)).status_code == 401
    assert not await cache.exists(key)


async def test_concurrent_send_only_sends_one_email(client):
    responses = await asyncio.gather(send(client), send(client))
    assert sorted(result.status_code for result in responses) == [202, 429]
    assert client.fixture_state['mail_calls'] == 1


async def test_concurrent_verification_issues_only_one_token(client):
    assert (await send(client)).status_code == 202
    body = {'email': 'reader@example.com', 'code': client.fixture_state['mail']['reader@example.com']}
    results = await asyncio.gather(*(client.post('/api/auth/email/verify', json=body) for _ in range(2)))
    assert sorted(result.status_code for result in results) == [200, 401]


async def test_wrong_attempts_are_bounded_and_expired_code_cannot_login(client):
    assert (await send(client)).status_code == 202
    correct = client.fixture_state['mail']['reader@example.com']
    wrong = '000000' if correct != '000000' else '111111'
    for _ in range(5):
        assert (await client.post('/api/auth/email/verify', json={'email': 'reader@example.com', 'code': wrong})).status_code == 401
    assert (await client.post('/api/auth/email/verify', json={'email': 'reader@example.com', 'code': correct})).status_code == 429
    await client.fixture_app.state.redis.delete(code_key('reader@example.com'))
    assert (await client.post('/api/auth/email/verify', json={'email': 'reader@example.com', 'code': correct})).status_code == 401


async def test_ip_rate_limit_is_shared_in_redis(client):
    for index in range(5):
        assert (await send(client, f'user{index}@example.com')).status_code == 202
    response = await send(client, 'sixth@example.com')
    assert response.status_code == 429
    assert int(response.headers['Retry-After']) > 0


async def test_code_expires_using_real_redis_ttl(client):
    assert (await send(client)).status_code == 202
    code = client.fixture_state['mail']['reader@example.com']
    await client.fixture_app.state.redis.pexpire(code_key('reader@example.com'), 5)
    await asyncio.sleep(.03)
    assert (await client.post('/api/auth/email/verify', json={'email': 'reader@example.com', 'code': code})).status_code == 401


async def test_failed_smtp_clears_reservation_without_leaking_exception(client, monkeypatch):
    from app.services import auth as service
    sender = service.send_code
    async def failed(*args, **kwargs):
        raise RuntimeError('fixture-secret-that-must-not-be-shown')
    monkeypatch.setattr(service, 'send_code', failed)
    response = await send(client)
    assert response.status_code == 502 and 'fixture-secret' not in response.text
    assert not await client.fixture_app.state.redis.exists(code_key('reader@example.com'))
    monkeypatch.setattr(service, 'send_code', sender)
    assert (await send(client)).status_code == 202


async def test_admin_bootstrap_and_logout_revokes_existing_jwt(client):
    response = await login(client, 'admin@example.com')
    assert response.status_code == 200
    assert response.json()['user']['role'] == 'admin'
    headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
    assert (await client.get('/api/auth/me', headers=headers)).status_code == 200
    assert (await client.post('/api/auth/logout', headers=headers)).status_code == 204
    assert (await client.get('/api/auth/me', headers=headers)).status_code == 401
    claims = jwt.decode(response.json()['access_token'], get_settings().jwt_secret, algorithms=['HS256'], issuer=get_settings().jwt_issuer)
    assert 0 < await client.fixture_app.state.redis.ttl('blog:revoked:' + claims['jti']) <= 3600


async def test_missing_required_token_claims_are_rejected(client):
    token = jwt.encode({'sub': '1', 'exp': datetime.now(timezone.utc)+timedelta(minutes=5)}, get_settings().jwt_secret, algorithm='HS256')
    assert (await client.get('/api/auth/me', headers={'Authorization': 'Bearer '+token})).status_code == 401


async def test_expired_signed_token_is_rejected(client, identities):
    token = jwt.encode({'sub': str(identities['admin']['id']), 'jti': 'a'*48,
                        'iss': get_settings().jwt_issuer, 'iat': datetime.now(timezone.utc)-timedelta(minutes=5),
                        'exp': datetime.now(timezone.utc)-timedelta(seconds=5)},
                       get_settings().jwt_secret, algorithm='HS256')
    assert (await client.get('/api/admin/users', headers={'Authorization': 'Bearer '+token})).status_code == 401


async def test_redis_outage_fails_closed_for_authenticated_requests(client, identities, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RedisConnectionError('fixture outage')
    monkeypatch.setattr(client.fixture_app.state.redis, 'exists', unavailable)
    assert (await client.get('/api/admin/users', headers=identities['admin']['headers'])).status_code == 503


async def test_viewer_cannot_manage_and_editor_cannot_manage_users(client, identities):
    reader, editor = identities['viewer']['headers'], identities['editor']['headers']
    assert (await client.get('/api/admin/routes', headers=reader)).json() == []
    assert (await client.get('/api/admin/posts', headers=reader)).status_code == 403
    assert (await client.get('/api/admin/users', headers=editor)).status_code == 403
    routes = (await client.get('/api/admin/routes', headers=editor)).json()
    assert 'Editor' in {route['component'] for route in routes}
    assert 'Users' not in {route['component'] for route in routes}


async def test_draft_publication_and_article_ownership(client, identities):
    payload = {'title': '异步写作', 'summary': '一段摘要', 'content': '# 标题', 'category': '技术', 'status': 'draft'}
    owner = identities['editor']['headers']
    response = await client.post('/api/admin/posts', json=payload, headers=owner)
    assert response.status_code == 201
    post_id = response.json()['id']
    assert (await client.get(f'/api/posts/{post_id}')).status_code == 404
    assert (await client.get('/api/posts')).json()['total'] == 0
    assert (await client.put(f'/api/admin/posts/{post_id}', json={**payload, 'status': 'published'}, headers=identities['other']['headers'])).status_code == 403
    assert (await client.put(f'/api/admin/posts/{post_id}', json={**payload, 'status': 'published'}, headers=owner)).status_code == 200
    assert (await client.get(f'/api/posts/{post_id}')).status_code == 200
    assert (await client.get('/api/posts', params={'q': '异步'})).json()['total'] == 1
    assert (await client.get('/api/posts', params={'q': '%'})).json()['total'] == 0
    assert (await client.delete(f'/api/admin/posts/{post_id}', headers=owner)).status_code == 204
    assert (await client.get(f'/api/posts/{post_id}')).status_code == 404


async def test_user_disable_and_role_changes_are_enforced_by_backend(client, identities):
    actor = identities['admin']['headers']
    target = identities['editor']
    assert (await client.patch(f'/api/admin/users/{target["id"]}', json={'role': 'viewer', 'is_active': True}, headers=actor)).status_code == 200
    assert (await client.get('/api/admin/posts', headers=target['headers'])).status_code == 403
    assert (await client.patch(f'/api/admin/users/{target["id"]}', json={'role': 'editor', 'is_active': False}, headers=actor)).status_code == 200
    assert (await client.get('/api/auth/me', headers=target['headers'])).status_code == 401
    assert (await client.patch(f'/api/admin/users/{identities["admin"]["id"]}', json={'role': 'viewer', 'is_active': False}, headers=actor)).status_code == 400


async def test_private_upload_confirmation_and_published_cdn_redirect(client, identities):
    owner = identities['editor']['headers']
    response = await client.post('/api/uploads/presign', json={'filename': 'image.png', 'contentType': 'image/png', 'size': 12}, headers=owner)
    assert response.status_code == 200
    asset_id = response.json()['id']
    call = client.fixture_state['cos_calls'][0]
    assert call['Method'] == 'PUT' and call['Expired'] == 300
    assert call['Headers'] == {'Content-Type': 'image/png', 'Content-Length': '12'}
    assert (await client.get(f'/api/media/{asset_id}')).status_code == 404
    assert (await client.post(f'/api/uploads/{asset_id}/complete', headers=identities['other']['headers'])).status_code == 404
    assert (await client.post(f'/api/uploads/{asset_id}/complete', headers=owner)).status_code == 200
    assert (await client.get(f'/api/uploads/{asset_id}/preview')).status_code == 401
    assert (await client.get(f'/api/uploads/{asset_id}/preview', headers=owner)).status_code == 200
    payload = {'title': '附件', 'summary': '私有附件', 'content': f'[[asset:{asset_id}]]', 'status': 'draft'}
    created = await client.post('/api/admin/posts', json=payload, headers=owner)
    assert created.status_code == 201
    post_id = created.json()['id']
    assert (await client.get(f'/api/media/{asset_id}')).status_code == 404
    assert (await client.put(f'/api/admin/posts/{post_id}', json={**payload, 'status': 'published'}, headers=owner)).status_code == 200
    media = await client.get(f'/api/media/{asset_id}', follow_redirects=False)
    assert media.status_code == 307
    assert media.headers['Cache-Control'] == 'private, no-store'
    assert media.headers['Referrer-Policy'] == 'no-referrer'
    target = urlsplit(media.headers['Location'])
    assert target.scheme == 'https' and target.hostname == 'cdn.example.com'
    assert set(parse_qs(target.query)) == {'sign', 't'}
    await client.delete(f'/api/admin/posts/{post_id}', headers=owner)
    assert (await client.get(f'/api/media/{asset_id}')).status_code == 404


async def test_wrong_object_metadata_is_rejected_and_cannot_be_published(client, identities):
    owner = identities['editor']['headers']
    response = await client.post('/api/uploads/presign', json={'filename': 'bad.png', 'contentType': 'image/png', 'size': 13}, headers=owner)
    asset_id = response.json()['id']
    assert (await client.post(f'/api/uploads/{asset_id}/complete', headers=owner)).status_code == 400
    async with SessionLocal() as db:
        assert (await db.get(Asset, asset_id)).state == 'rejected'
    assert (await client.post('/api/admin/posts', json={'title': 'Bad', 'summary': 'Bad', 'content': f'[[asset:{asset_id}]]'}, headers=owner)).status_code == 400
    assert (await client.post('/api/uploads/presign', json={'filename': 'bad.svg', 'contentType': 'image/svg+xml', 'size': 12}, headers=owner)).status_code == 422


async def test_anonymous_analytics_filters_query_and_referrer_data(client, identities):
    event = {'event': 'pageview', 'path': '/posts/1?email=private@example.com#secret', 'visitorId': 'a'*32, 'referrer': 'https://example.com/private?token=secret'}
    assert (await client.post('/api/analytics/events', json=event)).status_code == 202
    summary = await client.get('/api/analytics/summary', headers=identities['admin']['headers'])
    assert summary.json()['pv'] == 1 and summary.json()['uv'] == 1
    from app.models import Event
    async with SessionLocal() as db:
        row = await db.scalar(select(Event))
        assert row.path == '/posts/1' and row.referrer == 'https://example.com'
