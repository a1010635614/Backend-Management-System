"""Verified Compose release, backup and application rollback on a Linux host."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from artifact import ArtifactError, commit_id, extract, verify
from smoke import check


class DeployError(RuntimeError):
    pass


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

    def compose(self, release, *arguments, capture=False):
        commit_id(release.name)
        command = ['docker', 'compose', '--env-file', str(self.envfile), '-p', self.project,
                   '-f', str(release / 'deploy/docker/docker-compose.yml'),
                   '-f', str(release / 'deploy/docker/docker-compose.production.yml'),
                   '-f', str(release / 'deploy/docker/docker-compose.host.yml'), *arguments]
        environment = {**os.environ, 'RELEASE_TAG': release.name, 'BLOG_SHARED_ROOT': str(self.shared),
                       'GATEWAY_PORT': str(self.gateway_port), 'BACKEND_PORT': str(self.backend_port),
                       'COMPOSE_PARALLEL_LIMIT': '1'}
        return subprocess.run(command, env=environment, cwd=release, check=True, timeout=1800,
                              capture_output=capture)

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
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        path = self.backups / ('blog-' + stamp + '-' + release.name[:12] + '.dump')
        with path.open('xb') as stream:
            path.chmod(0o600)
            command = ['docker', 'compose', '--env-file', str(self.envfile), '-p', self.project,
                       '-f', str(release / 'deploy/docker/docker-compose.yml'), 'exec', '-T', 'postgres',
                       'sh', '-ec', 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc']
            subprocess.run(command, env={**os.environ, 'RELEASE_TAG': release.name}, stdout=stream,
                           stderr=subprocess.PIPE, check=True, timeout=300)
            stream.flush(); os.fsync(stream.fileno())
        if path.stat().st_size < 100:
            raise DeployError('Database backup is incomplete')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        atomic_text(path.with_suffix('.dump.sha256'), digest + '  ' + path.name + '\n')
        print('Database backup completed: ' + path.name, flush=True)

    def start(self, release):
        # Recreate only the one-shot migration so a previous exit 0 cannot skip it.
        self.compose(release, 'rm', '-s', '-f', 'migrate', capture=True)
        self.compose(release, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '180')
        return check('http://127.0.0.1:' + str(self.gateway_port), release, self.host)

    def deploy(self, directory, commit, initialize_empty=False):
        lock = self.root / '.deploy.lock'
        with lock.open('a') as stream:
            os.chmod(lock, 0o600)
            try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise DeployError('Another release is running') from None
            previous = self.previous()
            pending_link = self.root / '.current-next'
            if pending_link.exists() or pending_link.is_symlink():
                raise DeployError('Unexpected pending release link; inspect it before retrying')
            if previous is None and not initialize_empty and not (self.shared / 'database-import-verified.json').is_file():
                raise DeployError('First deployment requires a verified data import or explicit --initialize-empty')
            release = self.stage(directory, commit)
            self.compose(release, 'config', '--quiet')
            for service in ('redis', 'backend', 'frontend-web', 'frontend-admin', 'gateway'):
                self.compose(release, 'build', service)
            self.compose(release, 'up', '-d', '--no-build', '--pull', 'never', '--wait', 'postgres', 'redis')
            self.backup(release)
            self.assets(release)
            try:
                result = self.start(release)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                if previous is not None:
                    self.start(previous)
                    print('Previous Compose application restored; database was not downgraded.', flush=True)
                else:
                    self.compose(release, 'stop', 'gateway', 'backend', 'frontend-web', 'frontend-admin', capture=True)
                raise DeployError('Release did not pass health and asset checks') from None
            link = pending_link
            link.symlink_to(release)
            os.replace(link, self.root / 'current')
            atomic_text(self.root / '.current-release', commit + '\n')
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
    except (ArtifactError, DeployError, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('Compose release stopped. Inspect the failed step; secrets were not printed by the deployer.') from None
