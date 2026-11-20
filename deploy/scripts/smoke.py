"""Check public routes and exact release assets without credentials or side effects."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class SmokeError(RuntimeError):
    pass


def check(base, release, host=None):
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SmokeError('Invalid smoke-test address')
    base = base.rstrip('/')
    release = Path(release).resolve()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, status=200):
        headers = {'Host': host} if host else {}
        try:
            response = opener.open(urllib.request.Request(base + path, headers=headers), timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            data = response.read(5 * 1024 * 1024 + 1)
            if response.status != status or len(data) > 5 * 1024 * 1024:
                raise SmokeError('Unexpected status or length for ' + path)
            return data, response.headers

    health = json.loads(request('/api/health')[0])
    if any(health.get(key) != 'UP' for key in ('status', 'database', 'redis')):
        raise SmokeError('Database or Redis is not healthy')
    posts = json.loads(request('/api/posts')[0])
    if not isinstance(posts.get('items'), list) or not isinstance(posts.get('total'), int):
        raise SmokeError('Unexpected paginated article response')
    request('/api/admin/routes', 401)
    request('/api/auth/me', 401)
    specification = json.loads(request('/openapi.json')[0])
    if not {'/api/posts', '/api/admin/routes', '/api/auth/logout'} <= specification.get('paths', {}).keys():
        raise SmokeError('OpenAPI routes are incomplete')
    request('/docs')
    for name, prefix, deep in [('frontend-web', '', '/article/history-check'),
                               ('frontend-admin', '/admin', '/admin/articles/edit/123')]:
        expected = (release / name / 'dist/index.html').read_bytes()
        data, headers = request(prefix + '/')
        if data != expected or 'no-store' not in headers.get('Cache-Control', ''):
            raise SmokeError('The served HTML does not match the selected release')
        if request(deep)[0] != expected:
            raise SmokeError('History fallback failed')
        assets = re.findall(r'(?:src|href)="(' + re.escape(prefix) + r'/assets/[^"?#]+)"', data.decode())
        if not assets:
            raise SmokeError('The application has no entry assets')
        for path in assets:
            relative = path[len(prefix):].lstrip('/')
            actual, headers = request(path)
            expected_asset = (release / name / 'dist' / relative).read_bytes()
            if hashlib.sha256(actual).digest() != hashlib.sha256(expected_asset).digest():
                raise SmokeError('The served asset does not match the selected release')
            if 'immutable' not in headers.get('Cache-Control', ''):
                raise SmokeError('Hashed assets need immutable cache headers')
        request(prefix + '/assets/does-not-exist.js', 404)
    return {'health': 'UP', 'web': 'matched', 'admin': 'matched', 'history': 'passed',
            'authorization': 'passed', 'openapi': 'passed', 'articles': posts['total']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--host')
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.base, args.release, args.host), sort_keys=True))
    except (SmokeError, OSError, ValueError):
        raise SystemExit('Public smoke checks failed; no credentials were used.') from None
