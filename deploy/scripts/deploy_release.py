"""Verified Compose release, backup and application rollback on a Linux host."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from artifact import ArtifactError, commit_id, extract, verify
from database_tools import DatabaseError, PostgresClient, deployment_lock
from smoke import check


class DeployError(RuntimeError):
    pass


# Runtime.env owns these values. A Flow Runner's ambient environment must not
# accidentally redirect the database or replace an integration credential.
RUNTIME_KEYS = '''APP_ENV POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD DATABASE_URL
REDIS_PASSWORD REDIS_URL JWT_SECRET JWT_EXP_MINUTES ADMIN_EMAILS ALLOWED_HOSTS CORS_ORIGINS
AUTH_CAPTCHA_REQUIRED GEETEST_ID GEETEST_KEY MAIL_HOST MAIL_PORT MAIL_USERNAME MAIL_PASSWORD
MAIL_FROM COS_REGION COS_BUCKET COS_SECRET_ID COS_SECRET_KEY CDN_BASE_URL CDN_AUTH_KEY
BAIDU_HM_ID PYTHON_PACKAGE_INDEX DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH'''.split()


def protected_directory(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink() or path == Path('/'):
        raise DeployError('Deployment directories must be absolute and not linked')
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        raise DeployError('Deployment directory must be owned by the operator and not writable by others')
    return path


def atomic_text(path, value, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix='.release-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Deployment:
    def __init__(self, root, envfile, project, gateway_port, backend_port, host):
        self.root = protected_directory(root)
        self.releases = protected_directory(self.root / 'releases')
        self.shared = protected_directory(self.root / 'shared')
        self.backups = protected_directory(self.root / 'backups')
        self.envfile = Path(envfile).absolute()
        if (self.envfile.resolve() != self.envfile or not self.envfile.is_file() or
                self.envfile.stat().st_uid != os.getuid() or self.envfile.stat().st_mode & 0o077):
            raise DeployError('Supply an operator-owned regular runtime environment file with mode 0600')
        if not re.fullmatch('[a-z][a-z0-9-]{2,50}', project):
            raise DeployError('Invalid Compose project')
        if any(not 1024 <= port <= 65535 for port in (gateway_port, backend_port)) or gateway_port == backend_port:
            raise DeployError('Use two distinct unprivileged loopback ports')
        self.project, self.gateway_port, self.backend_port, self.host = project, gateway_port, backend_port, host

    def compose_settings(self, release):
        commit_id(release.name)
        command = ['docker', 'compose', '--env-file', str(self.envfile), '-p', self.project,
                   '-f', str(release / 'deploy/docker/docker-compose.yml'),
                   '-f', str(release / 'deploy/docker/docker-compose.production.yml'),
                   '-f', str(release / 'deploy/docker/docker-compose.host.yml')]
        environment = {**{key: value for key, value in os.environ.items() if key not in RUNTIME_KEYS},
                       'RELEASE_TAG': release.name, 'BLOG_SHARED_ROOT': str(self.shared),
                       'GATEWAY_PORT': str(self.gateway_port), 'BACKEND_PORT': str(self.backend_port),
                       'COMPOSE_PARALLEL_LIMIT': '1'}
        return command, environment

    def compose(self, release, *arguments, capture=False):
        command, environment = self.compose_settings(release)
        return subprocess.run([*command, *arguments], env=environment, cwd=release, check=True, timeout=1800,
                              capture_output=capture)

    def postgres_client(self, release):
        # Only non-secret database/user names are requested; no environment dump.
        result = self.compose(release, 'exec', '-T', 'postgres', 'sh', '-ec',
                              'printf "%s\\n%s\\n" "$POSTGRES_USER" "$POSTGRES_DB"', capture=True)
        names = result.stdout.decode().splitlines()
        if len(names) != 2: raise DeployError('PostgreSQL identity could not be read')
        command, environment = self.compose_settings(release)
        return PostgresClient([*command, 'exec', '-T', 'postgres'], *names, environment=environment)

    def previous(self):
        current = self.root / 'current'
        if not current.is_symlink():
            if current.exists(): raise DeployError('current must be the managed release symlink')
            return None
        path = current.resolve(strict=True)
        if path.parent != self.releases or not re.fullmatch('[a-f0-9]{40}', path.name):
            raise DeployError('Current release is outside the release directory')
        manifest = json.loads((path / '.release-manifest.json').read_text())
        if manifest.get('format') != 2 or manifest.get('schema_revision') != '0003' or manifest.get('commit') != path.name:
            raise DeployError('Previous release is not compatible with automatic application rollback')
        return path

    def stage(self, directory, commit):
        manifest = verify(directory, commit)
        release = self.releases / commit
        if release.exists():
            existing = json.loads((release / '.release-manifest.json').read_text())
            if existing != manifest:
                raise DeployError('Existing release does not match the immutable artifact')
            return release
        temporary = self.releases / ('.stage-' + commit)
        if temporary.exists(): raise DeployError('Inspect and remove the earlier incomplete stage before retrying')
        extract(directory, commit, temporary)
        atomic_text(temporary / '.release-manifest.json', json.dumps(manifest, sort_keys=True) + '\n')
        os.rename(temporary, release)
        return release

    def assets(self, release):
        for frontend, destination in [('frontend-web', 'web-assets'), ('frontend-admin', 'admin-assets')]:
            target = protected_directory(self.shared / destination)
            target.chmod(0o755)
            source = release / frontend / 'dist/assets'
            for item in source.rglob('*'):
                if not item.is_file() or item.is_symlink():
                    if item.is_dir(): continue
                    raise DeployError('Invalid frontend asset')
                output = target / item.relative_to(source)
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if output.exists():
                    if output.is_symlink() or hashlib.sha256(output.read_bytes()).digest() != hashlib.sha256(item.read_bytes()).digest():
                        raise DeployError('Hashed asset name conflicts with another release')
                else:
                    with output.open('xb') as stream, item.open('rb') as reader:
                        shutil.copyfileobj(reader, stream)
                    output.chmod(0o644)

    def backup(self, release):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = self.backups / ('blog-' + stamp + '-' + release.name[:12] + '.dump')
        metadata = self.postgres_client(release).dump(path, source_commit=release.name)
        atomic_text(path.with_suffix('.dump.sha256'), metadata['sha256'] + '  ' + path.name + '\n')
        print('Database backup completed: ' + path.name, flush=True)
        return path

    def start(self, release):
        # Recreate only the one-shot migration so a previous exit 0 cannot skip it.
        self.compose(release, 'rm', '-s', '-f', 'migrate', capture=True)
        self.compose(release, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '180')
        return check('http://127.0.0.1:' + str(self.gateway_port), release, self.host)

    def build(self, release):
        """Prepare images/assets before stopping writers; caller holds deployment_lock."""
        self.compose(release, 'config', '--quiet')
        for service in ('redis', 'backend', 'frontend-web', 'frontend-admin', 'gateway'):
            self.compose(release, 'build', service)
        self.assets(release)

    def publish(self, release):
        """Publish metadata after checks, without changing Nginx or database state."""
        pending = self.root / '.current-next'
        if pending.exists() or pending.is_symlink():
            raise DeployError('Unexpected pending release link; inspect it before retrying')
        pending.symlink_to(release)
        os.replace(pending, self.root / 'current')
        atomic_text(self.root / '.current-release', release.name + '\n')

    def import_verified(self, commit):
        marker = self.shared / 'database-import-verified.json'
        if (marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 32768 or
                marker.stat().st_uid != os.getuid() or marker.stat().st_mode & 0o077):
            return False
        try:
            value = json.loads(marker.read_text())
            return (isinstance(value, dict) and value.get('format') == 1 and
                    value.get('commit') == commit and value.get('project') == self.project and
                    value.get('source_schema') == '0002' and
                    re.fullmatch('[a-f0-9]{40}', str(value.get('source_commit', ''))) is not None and
                    re.fullmatch('[a-f0-9]{64}', str(value.get('archive_sha256', ''))) is not None)
        except (OSError, ValueError):
            return False

    def deploy(self, directory, commit, initialize_empty=False):
        with deployment_lock(self.root):
            previous = self.previous()
            pending_link = self.root / '.current-next'
            if pending_link.exists() or pending_link.is_symlink():
                raise DeployError('Unexpected pending release link; inspect it before retrying')
            if previous is None and not initialize_empty and not self.import_verified(commit):
                raise DeployError('First deployment requires a verified data import or explicit --initialize-empty')
            release = self.stage(directory, commit)
            self.build(release)
            self.compose(release, 'up', '-d', '--no-build', '--pull', 'never', '--wait', 'postgres', 'redis')
            self.backup(release)
            try:
                result = self.start(release)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                if previous is not None:
                    self.start(previous)
                    print('Previous Compose application restored; database was not downgraded.', flush=True)
                else:
                    self.compose(release, 'stop', 'gateway', 'backend', 'frontend-web', 'frontend-admin', capture=True)
                raise DeployError('Release did not pass health and asset checks') from None
            self.publish(release)
            print(json.dumps({'commit': commit, 'result': result, 'traffic_switch': 'host Nginx configuration'}), flush=True)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--root', default='/opt/blog-fullstack')
    parser.add_argument('--env-file', default='/opt/blog-fullstack/shared/runtime.env')
    parser.add_argument('--project', default='blog-production-v2')
    parser.add_argument('--gateway-port', type=int, default=18080)
    parser.add_argument('--backend-port', type=int, default=18000)
    parser.add_argument('--host', default='kongqi.xyz')
    parser.add_argument('--initialize-empty', action='store_true', help='Only for a new empty installation, never a native migration')
    args = parser.parse_args()
    deployment = Deployment(args.root, args.env_file, args.project, args.gateway_port, args.backend_port, args.host)
    deployment.deploy(args.artifacts, commit_id(args.commit), args.initialize_empty)


if __name__ == '__main__':
    try: main()
    except (ArtifactError, DeployError, DatabaseError, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('Compose release stopped. Inspect the failed step; secrets were not printed by the deployer.') from None
