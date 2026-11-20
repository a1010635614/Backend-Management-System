"""CDN preflight and atomic configuration. Receives secrets through SSH stdin."""
from contextlib import contextmanager
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx


class CdnCheckFailed(RuntimeError):
    """Contains only a public check name, never a URL, body or secret."""


@contextmanager
def deployment_lock():
    import fcntl
    with open('/opt/vueblog/.native-release.lock', 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CdnCheckFailed('another release/configuration is running') from None
        yield


def read_object(web, url, expected_size, expected_type):
    digest = sha256()
    size = 0
    with web.stream('GET', url) as response:
        if response.status_code != 200:
            raise CdnCheckFailed('signed object download status')
        if response.headers.get('content-type', '').split(';')[0].strip().lower() != expected_type:
            raise CdnCheckFailed('object content type mismatch')
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > expected_size:
                raise CdnCheckFailed('object exceeds declared size')
            digest.update(chunk)
        if size != expected_size:
            raise CdnCheckFailed('object size mismatch')
        # Only known response metadata is retained; signed URLs are never printed.
        cache = {key: response.headers[key] for key in
                 ('age', 'x-cache-lookup', 'x-cache', 'eo-cache-status')
                 if key in response.headers}
    return digest.hexdigest(), cache


def require_denied(web, url, check):
    with web.stream('GET', url) as response:
        if response.status_code != 403:
            raise CdnCheckFailed(check)


def verify_delivery(web, client, bucket, base_url, secret, assets, signer):
    """Check already-published objects; no uploads, deletes or database writes."""
    reports = []
    for asset in assets:
        origin = client.get_presigned_url(Bucket=bucket, Key=asset['key'], Method='GET', Expired=120)
        parts = urlsplit(origin)
        require_denied(web, urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')),
                       'COS anonymous access must be denied')
        expected, _ = read_object(web, origin, asset['size'], asset['content_type'])
        target = signer(base_url, asset['key'], secret)
        received, _ = read_object(web, target, asset['size'], asset['content_type'])
        repeated, cache = read_object(web, target, asset['size'], asset['content_type'])
        if received != expected or repeated != expected:
            raise CdnCheckFailed('CDN/COS content mismatch')
        signed = urlsplit(target)
        require_denied(web, urlunsplit((signed.scheme, signed.netloc, signed.path, '', '')),
                       'CDN unsigned warm-cache access must be denied')
        query = parse_qs(signed.query)
        signature = query['sign'][0]
        wrong = ('0' if signature[0] != '0' else '1') + signature[1:]
        invalid = urlunsplit((signed.scheme, signed.netloc, signed.path,
                             'sign=' + wrong + '&t=' + query['t'][0], ''))
        require_denied(web, invalid, 'CDN invalid signature must be denied')
        expired = signer(base_url, asset['key'], secret, timestamp=int(time.time()) - 600)
        require_denied(web, expired, 'CDN expired signature must be denied')
        reports.append({'content_type': asset['content_type'], 'bytes': asset['size'],
                        'content_matches': True, 'unsigned_invalid_expired_denied': True,
                        'cache_headers': cache})
    return reports


def public_assets(db, Asset, Post, select):
    chosen = []
    groups = (('image/jpeg', 'image/png', 'image/webp'), ('application/pdf',))
    for types in groups:
        rows = db.scalars(select(Asset).where(Asset.state == 'ready',
                                             Asset.content_type.in_(types)).order_by(Asset.size)).all()
        for asset in rows:
            if 0 < asset.size <= 10 * 1024 * 1024 and db.scalar(
                    select(Post.id).where(Post.content.contains('[[asset:' + asset.id + ']]')).limit(1)):
                chosen.append({'id': asset.id, 'key': asset.key, 'size': asset.size,
                               'content_type': asset.content_type})
                break
        else:
            raise CdnCheckFailed('publish one image and one PDF before CDN verification')
    return chosen


def application_ready(base_url, secret, asset, signer):
    for attempt in range(20):
        try:
            with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as web:
                health = web.get('http://127.0.0.1:8000/api/health')
                media = web.get('http://127.0.0.1:8000/api/media/' + asset['id'])
            if health.status_code == 200 and health.json().get('status') == 'UP' and media.status_code == 307:
                location = media.headers.get('location', '')
                issued = int(parse_qs(urlsplit(location).query)['t'][0])
                expected = signer(base_url, asset['key'], secret, timestamp=issued)
                if (abs(int(time.time()) - issued) <= 30 and hmac.compare_digest(location, expected)
                        and media.headers.get('cache-control') == 'private, no-store'
                        and media.headers.get('referrer-policy') == 'no-referrer'):
                    return True
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
        if attempt < 19:
            time.sleep(1)
    return False


def install_configuration(base_url, secret, asset, signer, envpath=Path('/etc/vueblog.env')):
    # Bound by the launcher to the existing, tested environment helpers.
    original = envpath.read_bytes()
    owner = envpath.stat()
    content = serialize_environment(original.decode(),
                                    {'CDN_BASE_URL': base_url, 'CDN_AUTH_KEY': secret}).encode()
    try:
        replace_file(envpath, content, owner)
        subprocess.run(['systemctl', 'restart', 'vueblog'], check=True, capture_output=True)
        if not application_ready(base_url, secret, asset, signer):
            raise CdnCheckFailed('application media redirect verification')
    except Exception:
        try:
            replace_file(envpath, original, owner)
            restored = subprocess.run(['systemctl', 'restart', 'vueblog'], capture_output=True)
        except Exception:
            raise CdnCheckFailed('configuration failed; restoration needs server inspection') from None
        if restored.returncode:
            raise CdnCheckFailed('original environment restored; service restart needs inspection') from None
        raise CdnCheckFailed('configuration failed; original environment restored and service restarted') from None


def main():
    payload = json.load(sys.stdin)
    base_url = payload.get('base_url', '')
    secret = payload.get('secret', '')
    if base_url != 'https://cdn.kongqi.xyz' or type(payload.get('apply')) is not bool:
        raise CdnCheckFailed('unexpected site or mode')
    with deployment_lock():
        from dotenv import dotenv_values
        root = Path('/opt/vueblog/current').resolve(strict=True)
        if root.parent != Path('/opt/vueblog/releases'):
            raise CdnCheckFailed('unexpected current release directory')
        values = dotenv_values('/etc/vueblog.env', interpolate=False)
        os.environ.update({key: value for key, value in values.items() if value is not None})
        sys.path.insert(0, str(root / 'backend'))
        from app.cdn import signed_cdn_url, validate_cdn_settings
        from app.main import Asset, Post, SessionLocal, cos_client
        from sqlalchemy import select
        from app.main import settings
        base_url = validate_cdn_settings(base_url, secret)
        envpath = Path('/etc/vueblog.env')
        before = envpath.stat()
        if before.st_uid != 0 or before.st_mode & 0o777 != 0o640:
            raise CdnCheckFailed('unexpected environment file permissions')
        with SessionLocal() as db:
            assets = public_assets(db, Asset, Post, select)
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as web:
            reports = verify_delivery(web, cos_client(), settings.cos_bucket,
                                      base_url, secret, assets, signed_cdn_url)
        print('CDN private-origin, content and authentication checks: PASS', flush=True)
        for report in reports:
            print(json.dumps(report, ensure_ascii=True), flush=True)
        if payload['apply']:
            install_configuration(base_url, secret, assets[0], signed_cdn_url, envpath)
            print('CDN configuration installed; health and signed media redirect: PASS', flush=True)
        else:
            print('Verification only; server configuration was not changed.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except CdnCheckFailed as error:
        raise SystemExit('CDN setup stopped: ' + str(error)) from None
    except ModuleNotFoundError:
        raise SystemExit('Deploy the CDN-capable backend through Flow before running this tool.') from None
    except Exception as error:
        # Transport exceptions can contain signed URLs. Never output their text.
        raise SystemExit('CDN setup stopped (' + type(error).__name__ + '); inspect server status before retrying.') from None
