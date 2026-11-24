"""Copy three digest-pinned official CI images to the user's private ACR repositories."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import getproxies
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'crpi-fdci37tiun8k5nzb.cn-hangzhou.personal.cr.aliyuncs.com'
TAGS = {'python': '3.12-slim-bookworm', 'node': '22-bookworm-slim', 'postgres': '16.15-bookworm'}


class SyncError(RuntimeError):
    def __init__(self, message, *, code=None):
        super().__init__(message)
        self.code = code


def transport_failure(raw):
    message = raw.decode('utf-8', errors='replace').lower()
    for code, fragments in (
        ('AUTH_REJECTED', ('unauthorized', 'authentication required', 'status code 401')),
        ('ACCESS_DENIED', ('denied', 'forbidden', 'status code 403')),
        ('NOT_FOUND', ('manifest_unknown', 'name_unknown', 'status code 404')),
        ('RATE_LIMIT', ('too many requests', 'toomanyrequests', 'status code 429')),
        ('TLS_FAILURE', ('certificate', 'tls handshake', 'x509:')),
        ('NETWORK_TIMEOUT', ('timeout', 'deadline exceeded', 'connection refused', 'no such host')),
        ('UNSUPPORTED_OPERATION', ('unsupported', 'not implemented')),
    ):
        if any(fragment in message for fragment in fragments):
            return code
    return 'TRANSPORT_FAILURE'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def loopback_proxy():
    proxy = getproxies().get('https') or getproxies().get('http')
    parsed = urlsplit(proxy or '')
    if (parsed.scheme in ('http', 'https') and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
            and not parsed.username and not parsed.password):
        return proxy
    return None


def require_repository_grants(token, repository):
    """Reject an explicitly unscoped JWT; the registry still verifies its signature."""
    parts = token.split('.')
    if len(parts) != 3:
        return  # Opaque tokens are checked by the registry itself.
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, UnicodeError):
        raise SyncError('ACR returned an unreadable token', code='AUTH_REJECTED') from None
    if not isinstance(claims, dict):
        raise SyncError('ACR returned unexpected token claims', code='AUTH_REJECTED')
    grants = claims.get('access')
    if grants is None:
        return
    if not isinstance(grants, list):
        raise SyncError('ACR returned unexpected token grants', code='AUTH_REJECTED')
    actions = set()
    for grant in grants:
        if (isinstance(grant, dict) and grant.get('type') == 'repository'
                and grant.get('name') == repository and isinstance(grant.get('actions'), list)):
            actions.update(action for action in grant['actions'] if isinstance(action, str))
    if not {'pull', 'push'} <= actions:
        raise SyncError('ACR token did not grant pull and push for the requested repository; '
                        'check the console login name, registry password and repository ownership',
                        code='REPOSITORY_PERMISSION_MISSING')


def registry_token(username, password, repository):
    """Exchange credentials only with the exact observed Aliyun token service."""
    if repository not in {'kongqi-blog/base-' + name for name in TAGS}:
        raise SyncError('Unexpected token repository')
    proxy = loopback_proxy()
    web = urllib.request.build_opener(urllib.request.ProxyHandler({'https': proxy} if proxy else {}), NoRedirect())
    try:
        try:
            response = web.open('https://' + REGISTRY + '/v2/', timeout=15)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise SyncError('ACR challenge HTTP ' + str(error.code)) from None
            response = error
        with response:
            challenge = response.headers.get('WWW-Authenticate', '')
        realm = re.search(r'realm="([^"]+)"', challenge)
        service = re.search(r'service="([^"]+)"', challenge)
        if not challenge.lower().startswith('bearer ') or not realm or realm[1] != 'https://dockerauth.cn-hangzhou.aliyuncs.com/auth' or not service:
            raise SyncError('Unexpected ACR authentication endpoint; credentials were not sent')
        query = urlencode({'service': service[1], 'scope': 'repository:' + repository + ':pull,push'})
        encoded = base64.b64encode((username + ':' + password).encode('utf-8')).decode('ascii')
        request = urllib.request.Request(realm[1] + '?' + query,
            headers={'Authorization': 'Basic ' + encoded, 'User-Agent': 'blog-acr-ci-sync'})
        try:
            with web.open(request, timeout=20) as response:
                raw = response.read(65537)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise SyncError('ACR rejected the username or repository password (HTTP ' + str(error.code) + ')',
                                code='AUTH_REJECTED') from None
            raise SyncError('ACR token service HTTP ' + str(error.code)) from None
        if len(raw) > 65536:
            raise SyncError('Unexpected ACR token response size')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise SyncError('Unexpected ACR token response')
        token = value.get('token') or value.get('access_token')
        if not isinstance(token, str) or not token or any(character.isspace() for character in token):
            raise SyncError('ACR did not return a valid registry token')
        require_repository_grants(token, repository)
        return token
    except (urllib.error.URLError, TimeoutError):
        raise SyncError('Direct ACR token request could not complete', code='NETWORK_TIMEOUT') from None


def validate_plan(value):
    if value.get('registry') != REGISTRY or value.get('namespace') != 'kongqi-blog':
        raise SyncError('Unexpected ACR destination')
    images = value.get('images', [])
    if len(images) != 3 or {item.get('name') for item in images} != set(TAGS):
        raise SyncError('Exactly the three reviewed CI images are required')
    for item in images:
        name, digest = item['name'], item.get('digest', '')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise SyncError('Use a full immutable image digest')
        if (item.get('source') != 'index.docker.io/library/' + name + '@' + digest
                or item.get('platform') != 'linux/amd64'
                or item.get('destination') != REGISTRY + '/kongqi-blog/base-' + name + ':' + TAGS[name]):
            raise SyncError('An image escaped its reviewed source, destination or platform')
    return images


def verified_oci(image):
    directory = ROOT / '.local/acr-oci' / image['name']
    if Path(image['oci_directory']).resolve() != directory or directory.resolve() != directory or directory.is_symlink():
        raise SyncError('Unexpected local OCI directory')
    index_path = directory / 'index.json'
    if index_path.is_symlink() or index_path.resolve() != index_path:
        raise SyncError('Unexpected OCI index path')
    index = json.loads(index_path.read_text())
    if len(index['manifests']) != 1 or index['manifests'][0]['digest'] != image['digest']:
        raise SyncError('Local OCI index differs from the source plan')
    def blob(digest, size=None):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise SyncError('Invalid OCI descriptor')
        path = directory / 'blobs/sha256' / digest.split(':', 1)[1]
        if path.is_symlink() or path.resolve() != path or not path.is_file() or (size is not None and path.stat().st_size != size):
            raise SyncError('Local OCI descriptor is incomplete')
        with path.open('rb') as stream:
            if 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise SyncError('Local OCI blob checksum differs')
        return path
    manifest = json.loads(blob(image['digest']).read_text())
    if manifest['config']['digest'] != image['config_digest']:
        raise SyncError('Local OCI config differs from the official source')
    for descriptor in [manifest['config'], *manifest['layers']]:
        blob(descriptor['digest'], descriptor['size'])
    config = json.loads(blob(manifest['config']['digest']).read_text())
    if config.get('os') != 'linux' or config.get('architecture') != 'amd64':
        raise SyncError('Local OCI platform differs')
    return directory


@contextmanager
def private_docker_config(parent):
    parent = Path(parent).resolve()
    with tempfile.TemporaryDirectory(prefix='acr-auth-', dir=parent) as directory:
        path = Path(directory)
        if os.name == 'nt':
            who = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, timeout=10)
            sid = re.search(r'S-1-5-21-[0-9-]+', who.stdout)
            if who.returncode or not sid:
                raise SyncError('Cannot establish the current Windows identity')
            secured = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                '*' + sid[0] + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], capture_output=True, timeout=15)
            if secured.returncode:
                raise SyncError('Cannot restrict the temporary credential directory')
        else:
            path.chmod(0o700)
        yield path


def credentials(username=None):
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    class Credentials(simpledialog.Dialog):
        def body(self, master):
            tk.Label(master, text='ACR 基础镜像同步\n目标：' + REGISTRY +
                     '\n将复制 Python、Node、PostgreSQL 官方 linux/amd64 镜像至 kongqi-blog 的三个私有仓库。'
                     '\n请填写“访问凭证”页的用户名与仓库固定密码。', justify='left').grid(row=0, columnspan=2, padx=12, pady=10)
            tk.Label(master, text='ACR 登录用户名').grid(row=1, column=0, padx=8)
            tk.Label(master, text='仓库固定密码').grid(row=2, column=0, padx=8)
            self.username = tk.Entry(master, width=54)
            self.password = tk.Entry(master, width=54, show='*')
            self.username.grid(row=1, column=1, padx=8, pady=5)
            self.password.grid(row=2, column=1, padx=8, pady=5)
            if username:
                self.username.insert(0, username)
                self.username.configure(state='readonly')
                return self.password
            return self.username

        def validate(self):
            username, password = self.username.get().strip(), self.password.get()
            if not username or len(username) > 256 or ':' in username or any(c.isspace() for c in username):
                messagebox.showerror('检查输入', '请填写访问凭证页面显示的登录用户名。', parent=self)
                return False
            if not password or len(password) > 1024 or any(c in password for c in '\r\n\x00'):
                messagebox.showerror('检查输入', '请填写刚设置的仓库固定密码。', parent=self)
                return False
            return True

        def apply(self):
            self.result = (self.username.get().strip(), self.password.get())

    window = tk.Tk()
    window.withdraw()
    window.attributes('-topmost', True)
    try:
        return Credentials(window, title='Blog ACR image synchronization').result
    finally:
        window.destroy()


def command(binary, arguments, environment, phase, *, stdin=None, timeout=900):
    # Capture transport output: registry errors can include signed blob URLs.
    started = time.monotonic()
    process = subprocess.Popen([str(binary), *arguments], env=environment, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        first = True
        while True:
            try:
                output, error = process.communicate(input=stdin if first else None, timeout=30)
                break
            except subprocess.TimeoutExpired:
                first = False
                elapsed = int(time.monotonic() - started)
                print(json.dumps({'phase': phase, 'elapsed_seconds': elapsed}), flush=True)
                if elapsed >= timeout:
                    process.kill()
                    process.communicate()
                    raise SyncError('Registry operation exceeded its time bound; inspect existing tags before retrying')
        if process.returncode:
            code = transport_failure(error)
            raise SyncError('Registry operation failed (' + code + ') during ' + phase, code=code)
        return output.decode('utf-8').strip()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def apply(plan, binary, username=None):
    images = validate_plan(plan)
    layouts = {image['name']: verified_oci(image) for image in images if 'oci_directory' in image}
    if layouts and len(layouts) != 3:
        raise SyncError('The offline plan must contain all three verified images')
    if not binary.is_file():
        raise SyncError('Install the checksum-verified Google crane CLI first')
    with private_docker_config(ROOT / '.local') as config:
        supplied = credentials(username)
        if supplied is None:
            return {'cancelled': True, 'registry_writes_performed': False}
        username, password = supplied
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() not in ('DOCKER_CONFIG', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')}
        environment['DOCKER_CONFIG'] = str(config)
        proxy = loopback_proxy()
        if proxy:
            environment.update(HTTPS_PROXY=proxy, HTTP_PROXY=proxy)
        # ACR delegates token authentication to dockerauth and blob storage to OSS.
        environment['NO_PROXY'] = '.aliyuncs.com'
        copied = []
        for item in images:
            name, target = item['name'], item['destination']
            token = registry_token(username, password, 'kongqi-blog/base-' + name)
            authfile = config / 'config.json'
            authfile.write_text(json.dumps({'auths': {REGISTRY: {'registrytoken': token}}}), encoding='utf-8')
            authfile.chmod(0o600)
            print(json.dumps({'phase': 'acr-token-received', 'image': name}), flush=True)
            print(json.dumps({'phase': 'copying', 'image': name, 'digest': item['digest']}), flush=True)
            if layouts:
                try:
                    existing = command(binary, ['digest', '--platform=linux/amd64', target], environment,
                                       'checking-existing-' + name, timeout=90)
                except SyncError as error:
                    if error.code != 'NOT_FOUND':
                        raise
                    existing = None
                if existing is not None and existing != item['digest']:
                    raise SyncError('Existing ACR tag differs; no tag was overwritten')
                if existing is None:
                    command(binary, ['push', '--platform=linux/amd64', str(layouts[name]), target],
                            environment, 'uploading-' + name)
            else:
                command(binary, ['copy', '--platform=linux/amd64', '--jobs=2', '--no-clobber', item['source'], target],
                        environment, 'copying-' + name)
            digest = command(binary, ['digest', '--platform=linux/amd64', target], environment, 'verifying-' + name, timeout=90)
            if digest != item['digest']:
                raise SyncError('Target digest differs; an existing tag was not overwritten')
            copied.append({**item, 'verified': True, 'ci_reference': target.split(':', 1)[0] + '@' + digest})
            print(json.dumps({'phase': 'image-verified', 'image': name, 'digest': digest}), flush=True)
    # The temporary directory, including registry credentials, has now been deleted.
    return {'registry': REGISTRY, 'images': copied, 'temporary_credentials_removed': True,
            'scope': 'CI development and testing', 'production_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'deploy/cicd/acr-images.json')
    parser.add_argument('--crane', type=Path, default=ROOT / '.local/tools/crane/crane.exe')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--username', help='Login name copied from the ACR console; never a password')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    validate_plan(plan)
    if not args.apply:
        print(json.dumps({'registry': REGISTRY, 'images': plan['images'], 'login_attempted': False,
                          'registry_writes_performed': False, 'credentials_requested': False}))
        return
    result = apply(plan, args.crane.resolve(), args.username)
    (ROOT / '.local/acr-mirror-result.json').write_text(json.dumps(result) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except SyncError as error:
        raise SystemExit(str(error) + '. Credentials and raw transport errors were not logged.') from None
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit('ACR synchronization stopped. No credentials or raw transport errors were logged; inspect the existing result before retrying.') from None
