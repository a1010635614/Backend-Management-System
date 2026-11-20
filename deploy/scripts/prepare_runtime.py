"""Plan or explicitly prepare the new production runtime; never a candidate config."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import secrets

from database_tools import write_json
from deploy_release import protected_directory

SOURCE = Path('/etc/vueblog.env')
DESTINATION = Path('/opt/blog-fullstack/shared/runtime.env')
COPY_KEYS = ('ADMIN_EMAILS', 'MAIL_HOST', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_FROM',
             'GEETEST_ID', 'GEETEST_KEY', 'COS_REGION', 'COS_BUCKET', 'COS_SECRET_ID', 'COS_SECRET_KEY',
             'CDN_BASE_URL', 'CDN_AUTH_KEY', 'BAIDU_HM_ID')
GENERATED_KEYS = ('POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET')
HOST = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')


def plan():
    # This function must not stat/open the source, inspect containers or call a provider.
    return {'source': str(SOURCE), 'destination': str(DESTINATION), 'target': 'new production only',
            'copy_keys': list(COPY_KEYS), 'generate_fresh': list(GENERATED_KEYS),
            'excluded': ['old DATABASE_URL', 'old JWT_SECRET', 'GitHub credentials', 'Feishu credentials'],
            'source_modified': False, 'services_restarted': False}


def literal_environment(values):
    lines = []
    for key, value in values.items():
        if not re.fullmatch('[A-Z][A-Z0-9_]*', key) or not isinstance(value, str):
            raise ValueError('Invalid runtime entry')
        if any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError('Runtime values must be single-line ASCII')
        # JSON quoting preserves quotes/backslashes. Compose $$ means a literal $.
        lines.append(key + '=' + json.dumps(value.replace('$', '$$')) + '\n')
    return ''.join(lines)


def build_values(original, host='kongqi.xyz'):
    from dotenv import dotenv_values
    if not HOST.fullmatch(host): raise ValueError('Use the verified public production hostname')
    values = dotenv_values(stream=io.StringIO(original), interpolate=False)
    copied = {key: values.get(key) for key in COPY_KEYS}
    if any(not isinstance(value, str) or not value.strip() for value in copied.values()):
        raise ValueError('A required existing integration setting is missing; no values were printed')
    if copied['MAIL_PORT'] not in ('465', '587'):
        raise ValueError('Confirm the existing TLS SMTP port before migration')
    if not re.fullmatch('[a-f0-9]{32}', copied['BAIDU_HM_ID']):
        raise ValueError('The public analytics ID is invalid')
    if not re.fullmatch(r'https://[a-z0-9.-]+', copied['CDN_BASE_URL']):
        raise ValueError('The existing CDN origin URL must use HTTPS without path or credentials')
    password, redis_password, jwt = (secrets.token_hex(32) for _ in range(3))
    result = {
        'APP_ENV': 'production', 'POSTGRES_DB': 'blog', 'POSTGRES_USER': 'blog',
        'POSTGRES_PASSWORD': password, 'DATABASE_URL': f'postgresql+asyncpg://blog:{password}@postgres:5432/blog',
        'REDIS_PASSWORD': redis_password, 'REDIS_URL': f'redis://:{redis_password}@redis:6379/0',
        'JWT_SECRET': jwt, 'ALLOWED_HOSTS': host + ',localhost,127.0.0.1',
        'CORS_ORIGINS': 'https://' + host, 'AUTH_CAPTCHA_REQUIRED': 'true',
        'GATEWAY_PORT': '18080', 'BACKEND_PORT': '18000', **copied}
    # Validate the allowed character set before opening any file for writing.
    literal_environment(result)
    return result


def prepare(source=SOURCE, destination=DESTINATION, *, host='kongqi.xyz'):
    if os.getuid() != 0: raise ValueError('Production preparation requires root')
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if source == destination or destination.exists() or destination.is_symlink():
        raise ValueError('The destination must be new; existing settings were preserved')
    if (source.resolve() != source or not source.is_file() or source.stat().st_uid != 0 or
            source.stat().st_mode & 0o027 or source.stat().st_size > 65536):
        raise ValueError('The source runtime file is not protected')
    # Read only here, after the caller has obtained explicit migration authorization.
    values = build_values(source.read_text(), host)
    parent = protected_directory(destination.parent)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(literal_environment(values)); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    write_json(parent / 'runtime-prepared.json', {
        'format': 1, 'source': str(source), 'destination': str(destination),
        'host': host, 'copied_keys': list(COPY_KEYS), 'generated_keys': list(GENERATED_KEYS),
        'source_modified': False, 'services_restarted': False})
    return {'prepared': True, 'destination': str(destination), 'copied_keys': list(COPY_KEYS)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--copy-production-integrations', action='store_true', help='Explicitly acknowledge the reviewed production-only copy')
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps(plan(), ensure_ascii=False, indent=2))
    elif not args.copy_production_integrations:
        raise SystemExit('Explicit authorization for the displayed production-only integration copy is required')
    else:
        try: print(json.dumps(prepare(), ensure_ascii=False))
        except Exception:
            raise SystemExit('Production runtime preparation did not complete. Inspect the destination; no settings or secrets were printed') from None
