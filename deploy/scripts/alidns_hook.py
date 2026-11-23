"""Certbot DNS-01 hooks for the single approved zone; credentials never enter argv."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

ZONE = 'kongqi.xyz'
RR = '_acme-challenge'
ENDPOINT = 'https://alidns.aliyuncs.com/'
ACTIONS = {'DescribeDomainRecords', 'DescribeDomainRecordInfo', 'AddDomainRecord', 'DeleteDomainRecord'}
CONFIG = Path('/etc/letsencrypt/alidns-hook.json')
STATE = Path('/var/lib/blog-acme')


class HookError(RuntimeError):
    """Only deliberate, redacted messages from this type may reach the terminal."""


class ApiError(HookError):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', code) else 'InvalidResponse'
        super().__init__('AliDNS API rejected the request: ' + self.code)


def encode(value):
    return quote(str(value), safe='~')


def signed_parameters(parameters, key_id, secret, *, nonce=None, timestamp=None):
    """Alibaba Cloud RPC signature v1; POST body and signing share RFC3986 encoding."""
    values = {**parameters, 'AccessKeyId': key_id, 'Version': '2015-01-09', 'Format': 'JSON',
              'SignatureMethod': 'HMAC-SHA1', 'SignatureVersion': '1.0',
              'SignatureNonce': nonce or uuid.uuid4().hex,
              'Timestamp': timestamp or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    canonical = '&'.join(encode(key) + '=' + encode(value) for key, value in sorted(values.items()))
    message = ('POST&%2F&' + encode(canonical)).encode()
    values['Signature'] = base64.b64encode(hmac.new((secret + '&').encode(), message, hashlib.sha1).digest()).decode()
    return values


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise HookError('AliDNS redirects are refused')


class AliDNS:
    def __init__(self, key_id, secret):
        self.key_id, self.secret = key_id, secret
        # Never use an ambient proxy or follow a redirect carrying this signed body.
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

    def call(self, action, **parameters):
        if action not in ACTIONS:
            raise HookError('AliDNS action is outside the hook allowlist')
        values = signed_parameters({'Action': action, **parameters}, self.key_id, self.secret)
        body = '&'.join(encode(key) + '=' + encode(value) for key, value in sorted(values.items())).encode()
        request = Request(ENDPOINT, data=body, method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with self.opener.open(request, timeout=15) as response:
                payload = response.read(65537)
        except HTTPError as error:
            try:
                payload = error.read(65537)
            finally:
                error.close()
            try:
                value = json.loads(payload) if len(payload) <= 65536 else {}
            except (ValueError, UnicodeError):
                value = {}
            raise ApiError(value.get('Code') if isinstance(value, dict) else None) from None
        except (URLError, TimeoutError, OSError):
            # Do not print exception text: it may contain URLs or request data.
            raise HookError('AliDNS transport failed; inspect the protected action state before retrying a write') from None
        try:
            value = json.loads(payload) if len(payload) <= 65536 else None
        except (ValueError, UnicodeError):
            value = None
        if not isinstance(value, dict):
            raise HookError('AliDNS returned an invalid response')
        if 'Code' in value:
            raise ApiError(value['Code'])
        return value

    def challenge_records(self):
        records = []
        for page in range(1, 21):
            value = self.call('DescribeDomainRecords', DomainName=ZONE, RRKeyWord=RR,
                              Type='TXT', PageNumber=page, PageSize=100)
            batch = value.get('DomainRecords', {}).get('Record')
            total = value.get('TotalCount')
            if not isinstance(batch, list) or type(total) is not int or total < 0:
                raise HookError('AliDNS returned invalid record pagination')
            records.extend(item for item in batch if isinstance(item, dict) and item.get('RR') == RR and item.get('Type') == 'TXT')
            if page * 100 >= total:
                return records
            if not batch:
                raise HookError('AliDNS record pagination stopped early')
        raise HookError('Too many challenge records; inspect the zone manually')


def protected_json(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise HookError('Configuration/state paths must not be linked')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    info.st_mode & 0o077 or info.st_size > 16384):
                raise HookError('Configuration/state must be operator-owned regular files with mode 0600')
            value = json.loads(stream.read(16385))
    except (OSError, ValueError, UnicodeError):
        raise HookError('Protected configuration/state could not be read') from None
    if not isinstance(value, dict):
        raise HookError('Protected configuration/state is invalid')
    return value


def load_client(path):
    return client_from_credentials(protected_json(path))


def client_from_credentials(value):
    if not isinstance(value, dict) or set(value) != {'access_key_id', 'access_key_secret'}:
        raise HookError('AliDNS credentials must contain only the two documented fields')
    for key in value:
        if not isinstance(value[key], str) or not re.fullmatch(r'[A-Za-z0-9+/=_-]{12,128}', value[key]):
            raise HookError('AliDNS credential format is invalid')
    return AliDNS(value['access_key_id'], value['access_key_secret'])


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        if self.directory.resolve() != self.directory or self.directory.is_symlink():
            raise HookError('State directory must not be linked')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise HookError('State directory must be operator-owned with mode 0700')

    @contextmanager
    def lock(self):
        import fcntl
        fd = os.open(self.directory / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.geteuid() or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode):
                raise HookError('State lock is not protected')
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HookError('Another DNS hook is active; no DNS action was taken') from None
            yield

    def path(self, validation):
        return self.directory / (hashlib.sha256((ZONE + '\n' + validation).encode()).hexdigest() + '.json')

    def read(self, validation):
        path = self.path(validation)
        if not path.exists() and not path.is_symlink():
            return None
        value = protected_json(path)
        if (value.get('format') != 1 or value.get('domain') != ZONE or value.get('rr') != RR or
                value.get('type') != 'TXT' or value.get('validation') != validation):
            raise HookError('Challenge state does not match this Certbot invocation')
        return value

    def write(self, validation, value):
        fd, temporary = tempfile.mkstemp(prefix='.dns-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path(validation))
            directory = os.open(self.directory, os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)


def invocation(environment):
    domain = environment.get('CERTBOT_IDENTIFIER', environment.get('CERTBOT_DOMAIN', '')).lower().rstrip('.')
    legacy = environment.get('CERTBOT_DOMAIN', domain).lower().rstrip('.')
    if domain != ZONE or legacy != domain:
        raise HookError('This hook only handles the approved base domain')
    validation = environment.get('CERTBOT_VALIDATION', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', validation):
        raise HookError('Certbot validation is missing or invalid')
    return validation


def dig(*arguments):
    try:
        result = subprocess.run(['/usr/bin/dig', *arguments], capture_output=True, text=True,
                                timeout=8, check=True)
    except (OSError, subprocess.SubprocessError):
        raise HookError('Authoritative DNS query failed; ensure dnsutils and outbound DNS are available') from None
    if len(result.stdout) > 65536:
        raise HookError('DNS response exceeded the hook limit')
    return result.stdout


def nameservers():
    values = [line.strip().lower().rstrip('.') for line in dig('+time=2', '+tries=1', '+short', 'NS', ZONE).splitlines() if line.strip()]
    pattern = r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'
    if not 1 <= len(values) <= 12 or any(not re.fullmatch(pattern, name) for name in values):
        raise HookError('Authoritative nameserver discovery failed')
    return sorted(set(values))


def authoritative_value(response, validation):
    """Accept only an authoritative, successful TXT answer at the exact owner."""
    if 'status: NOERROR,' not in response:
        return False
    flags = re.search(r';; flags: ([^;]+);', response)
    if not flags or 'aa' not in flags.group(1).split():
        return False
    for line in response.splitlines():
        fields = line.split(None, 4)
        if (len(fields) == 5 and fields[0].lower().rstrip('.') == RR + '.' + ZONE and
                fields[2:4] == ['IN', 'TXT'] and fields[4] == '"' + validation + '"'):
            return True
    return False


def wait_for_dns(validation, seconds=300):
    if not 10 <= seconds <= 900:
        raise HookError('DNS propagation timeout must be between 10 and 900 seconds')
    authorities = nameservers()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        visible = True
        for server in authorities:
            try:
                response = dig('@' + server, '+tcp', '+time=2', '+tries=1', '+norecurse',
                               '+noall', '+comments', '+answer', RR + '.' + ZONE, 'TXT')
                visible = authoritative_value(response, validation) and visible
            except HookError:
                visible = False
        if visible:
            return
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise HookError('TXT did not become visible on every authoritative nameserver before the deadline')


def cleanup(client, journal, validation):
    value = journal.read(validation)
    if value is None or value.get('phase') == 'cleaned':
        return
    record_id = value.get('record_id')
    if not isinstance(record_id, str) or not re.fullmatch(r'[0-9]{1,64}', record_id):
        raise HookError('A DNS write has uncertain ownership; protected state retained for operator inspection')
    try:
        actual = client.call('DescribeDomainRecordInfo', RecordId=record_id)
    except ApiError as error:
        if error.code != 'InvalidRecordId.NotFound':
            raise
    else:
        expected = {'RecordId': record_id, 'DomainName': ZONE, 'RR': RR, 'Type': 'TXT', 'Value': validation, 'Line': 'default'}
        if any(actual.get(key) != entry for key, entry in expected.items()):
            raise HookError('TXT identity changed; no DNS record was deleted')
        value['phase'] = 'deleting'; journal.write(validation, value)
        result = client.call('DeleteDomainRecord', RecordId=record_id)
        if result.get('RecordId') != record_id:
            raise HookError('DNS deletion was not acknowledged; protected state retained')
    value['phase'] = 'cleaned'; journal.write(validation, value)


def authenticate(client, journal, validation, waiter=wait_for_dns, seconds=300):
    if type(seconds) is not int or not 10 <= seconds <= 900:
        raise HookError('DNS propagation timeout must be between 10 and 900 seconds')
    value = journal.read(validation)
    if value is None:
        if any(record.get('Value') == validation for record in client.challenge_records()):
            raise HookError('An identical TXT already exists without an ownership journal; nothing was changed')
        value = {'format': 1, 'domain': ZONE, 'rr': RR, 'type': 'TXT', 'validation': validation, 'phase': 'creating'}
        journal.write(validation, value)
        # Never blindly retry AddDomainRecord after a lost/uncertain response.
        result = client.call('AddDomainRecord', DomainName=ZONE, RR=RR, Type='TXT', Value=validation, TTL=600, Line='default')
        record_id = result.get('RecordId')
        if not isinstance(record_id, str) or not re.fullmatch(r'[0-9]{1,64}', record_id):
            raise HookError('DNS creation has uncertain ownership; protected state retained')
        value.update(record_id=record_id, phase='created'); journal.write(validation, value)
    elif value.get('phase') not in ('created', 'visible'):
        raise HookError('An earlier DNS action needs inspection; it will not be retried automatically')
    try:
        waiter(validation, seconds)
    except HookError:
        try: cleanup(client, journal, validation)
        except HookError:
            raise HookError('Propagation failed and TXT cleanup needs operator inspection; protected state retained') from None
        raise
    value['phase'] = 'visible'; journal.write(validation, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'auth', 'cleanup'))
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--state-dir', type=Path, default=STATE)
    parser.add_argument('--propagation-timeout', type=int, default=300)
    args = parser.parse_args()
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        raise HookError('Run the installed Certbot hook as root')
    client = load_client(args.config)
    journal = Journal(args.state_dir)
    with journal.lock():
        if args.action == 'check':
            client.challenge_records(); nameservers()
            print('AliDNS read permission and DNS discovery passed; no record was changed.')
        else:
            validation = invocation(os.environ)
            if args.action == 'auth':
                authenticate(client, journal, validation, seconds=args.propagation_timeout)
            else:
                cleanup(client, journal, validation)
            print('AliDNS ' + args.action + ' completed.', file=sys.stderr)


if __name__ == '__main__':
    try: main()
    except HookError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit('DNS hook failed; inspect protected state. Credentials and request data were not printed.') from None
