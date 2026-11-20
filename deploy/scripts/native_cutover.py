"""First native-to-Compose cutover; rollback to the old DB stops at traffic exposure."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from artifact import ArtifactError, commit_id
from database_tools import DatabaseError, PostgresClient, deployment_lock, write_json
from deploy_release import Deployment, DeployError, atomic_text
from smoke import check


class CutoverError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(value).hexdigest()


@contextmanager
def native_locks(native_root, backup_root):
    """Cooperate with the existing native publisher and backup, never replace locks."""
    import fcntl
    handles = []
    try:
        for directory, name in ((Path(native_root), '.native-release.lock'), (Path(backup_root), '.backup.lock')):
            if (directory.resolve() != directory or not directory.is_dir() or
                    directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022):
                raise CutoverError('The native lock directory is not protected')
            fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            handle = os.fdopen(fd, 'a'); handles.append(handle)
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise CutoverError('Unexpected native lock file')
            try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise CutoverError('A native deployment or backup is running') from None
        yield
    finally:
        for handle in reversed(handles): handle.close()


class NativeHost:
    def __init__(self, native_root='/opt/vueblog', nginx_site='/etc/nginx/sites-available/vueblog',
                 backup_root='/var/backups/vueblog'):
        self.root, self.site, self.backup_root = map(Path, (native_root, nginx_site, backup_root))

    def active(self):
        result = subprocess.run(['systemctl', 'is-active', '--quiet', 'vueblog.service'],
                                capture_output=True, timeout=15)
        if result.returncode not in (0, 3): raise CutoverError('Native service state is unknown')
        return result.returncode == 0

    def service(self, action):
        if action not in ('stop', 'start'): raise CutoverError('Unexpected native service action')
        subprocess.run(['systemctl', action, 'vueblog.service'], check=True, capture_output=True, timeout=60)
        if self.active() != (action == 'start'): raise CutoverError('Native service did not reach the required state')

    def nginx_check(self):
        subprocess.run(['nginx', '-t'], capture_output=True, check=True, timeout=15)

    def nginx_reload(self):
        subprocess.run(['systemctl', 'reload', 'nginx.service'], capture_output=True, check=True, timeout=30)

    def preflight(self, host):
        if os.getuid() != 0: raise CutoverError('Run the reviewed cutover as root')
        if (self.root.resolve() != self.root or not self.root.is_dir() or
                self.root.stat().st_uid != 0 or self.root.stat().st_mode & 0o022):
            raise CutoverError('Unexpected native application directory')
        if (self.site.resolve() != self.site or not self.site.is_file() or
                self.site.stat().st_uid != 0 or self.site.stat().st_mode & 0o022 or self.site.stat().st_size > 131072):
            raise CutoverError('Unexpected native Nginx site file')
        enabled = Path('/etc/nginx/sites-enabled/vueblog')
        if not enabled.is_symlink() or enabled.resolve() != self.site:
            raise CutoverError('The active native Nginx site differs')
        for name in ('fullchain.pem', 'privkey.pem'):
            if not (Path('/etc/letsencrypt/live') / host / name).is_file():
                raise CutoverError('The current HTTPS certificate is not available')
        if not self.active(): raise CutoverError('The old application must be healthy before planning a cutover')
        self.nginx_check()
        marker = self.root / '.current-release'
        if marker.is_symlink() or marker.stat().st_size > 100: raise CutoverError('Invalid native release marker')
        return commit_id(marker.read_text().strip()), self.site.read_bytes()


class NativeCutover:
    def __init__(self, deployment, host, source):
        self.deployment, self.host, self.source = deployment, host, source
        self.work = deployment.shared / 'native-migration'
        self.state = None
        self.exposed = False

    def record(self, phase, **fields):
        self.state.update(phase=phase, updated_at=datetime.now(timezone.utc).isoformat(), **fields)
        write_json(self.work / 'state.json', self.state)

    def apply(self, directory, commit):
        commit = commit_id(commit)
        deployment, host, source = self.deployment, self.host, self.source
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', deployment.host):
            raise CutoverError('Use the verified production DNS hostname')
        with deployment_lock(deployment.root), native_locks(host.root, host.backup_root):
            if (deployment.previous() is not None or (deployment.shared / 'traffic-ready.json').exists() or
                    (deployment.shared / 'database-import-verified.json').exists() or
                    self.work.exists() or self.work.is_symlink()):
                raise CutoverError('An existing Compose release or cutover journal requires inspection; do not replay the migration')
            source_commit, old_site = host.preflight(deployment.host)
            if source.revision() != '0002': raise CutoverError('The native source must be the verified 0002 schema')
            release = deployment.stage(directory, commit)
            template = (release / 'deploy/nginx/https.conf.template').read_text()
            new_site = template.replace('__DOMAIN__', deployment.host).replace('__GATEWAY_PORT__', str(deployment.gateway_port))
            if '__DOMAIN__' in new_site or '__GATEWAY_PORT__' in new_site:
                raise CutoverError('Nginx configuration was not rendered')
            # No interruption of the old site while validating configuration/build inputs.
            deployment.build(release)
            deployment.compose(release, 'up', '-d', '--no-build', '--pull', 'never', '--wait', 'postgres', 'redis')
            target = deployment.postgres_client(release)
            if target.revision() is not None: raise CutoverError('Compose database is not empty; no data was replaced')
            self.work.mkdir(mode=0o700)
            atomic_text(self.work / 'nginx.before.conf', old_site.decode())
            atomic_text(self.work / 'nginx.compose.conf', new_site)
            self.state = {'format': 1, 'commit': commit, 'source_commit': source_commit,
                          'project': deployment.project, 'host': deployment.host,
                          'gateway_port': deployment.gateway_port, 'nginx_before_sha256': digest(old_site),
                          'nginx_compose_sha256': digest(new_site.encode()), 'traffic_may_have_changed': False}
            self.record('prepared')
            freeze_attempted, config_attempted = False, False
            try:
                self.record('stopping-native')
                freeze_attempted = True
                host.service('stop')
                self.record('native-stopped')
                frozen = source.fingerprint()
                legacy = source.fingerprint(legacy_data=True)
                archive = self.work / 'native-final.dump'
                metadata = source.dump(archive, source_commit=source_commit)
                if metadata['schema'] != '0002' or source.fingerprint() != frozen:
                    raise CutoverError('Source data changed during the final backup')
                restored = target.restore_empty(archive, metadata)
                if restored != frozen: raise CutoverError('Imported database differs from the frozen source')
                self.record('import-verified', archive_sha256=metadata['sha256'], fingerprint=frozen)
                write_json(deployment.shared / 'database-import-verified.json', {
                    'format': 1, 'commit': commit, 'project': deployment.project, 'source_commit': source_commit,
                    'source_schema': '0002', 'archive_sha256': metadata['sha256'], 'fingerprint': frozen})
                deployment.start(release)
                if target.revision() != '0003' or target.fingerprint(legacy_data=True) != legacy:
                    raise CutoverError('Upgrade did not preserve the imported business data')
                # Check the old DB a final time; cooperating publishers are blocked by native_locks.
                if host.active() or source.fingerprint() != frozen:
                    raise CutoverError('Native writers resumed before cutover')
                deployment.backup(release)
                self.record('compose-checked')
                if digest(host.site.read_bytes()) != self.state['nginx_before_sha256']:
                    raise CutoverError('Nginx site changed concurrently')
                config_attempted = True
                atomic_text(host.site, new_site, 0o644)
                host.nginx_check()
                # Persist BEFORE reload: timeout/failure may still mean traffic reached the new DB.
                self.record('reload-attempted', traffic_may_have_changed=True)
                self.exposed = True
                host.nginx_reload()
                result = check('https://' + deployment.host, release, deployment.host)
                deployment.publish(release)
                write_json(deployment.shared / 'traffic-ready.json', {
                    'project': deployment.project, 'gateway_port': deployment.gateway_port, 'host': deployment.host})
                self.record('complete')
                return {'commit': commit, 'source_commit': source_commit, 'cutover': 'passed', 'result': result}
            except BaseException:
                if self.exposed:
                    self.record('recovery-required', traffic_may_have_changed=True)
                    raise CutoverError('Traffic may have reached Compose. Native remains stopped; recover using the NEW database, never silently switch to the old copy') from None
                recovery_errors = []
                if config_attempted:
                    try:
                        atomic_text(host.site, old_site.decode(), 0o644)
                        host.nginx_check()
                    except BaseException: recovery_errors.append('nginx-configuration')
                try:
                    deployment.compose(release, 'stop', 'gateway', 'backend', 'frontend-web', 'frontend-admin', capture=True)
                except BaseException: recovery_errors.append('candidate-stop')
                if freeze_attempted:
                    try: host.service('start')
                    except BaseException: recovery_errors.append('native-start')
                (deployment.shared / 'database-import-verified.json').unlink(missing_ok=True)
                self.record('aborted-before-cutover', recovery_errors=recovery_errors)
                raise CutoverError('Cutover stopped before exposure. Inspect the journal and retained database; automatic replay is disabled') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--root', default='/opt/blog-fullstack')
    parser.add_argument('--env-file', default='/opt/blog-fullstack/shared/runtime.env')
    parser.add_argument('--project', default='blog-production-v2')
    parser.add_argument('--gateway-port', type=int, default=18080)
    parser.add_argument('--backend-port', type=int, default=18000)
    parser.add_argument('--host', default='kongqi.xyz')
    parser.add_argument('--apply', action='store_true', help='Stop native writes, import data and switch production traffic')
    args = parser.parse_args()
    if not args.apply: raise SystemExit('Review FIRST-CUTOVER.md and the exact runtime configuration before explicitly applying this migration')
    try:
        deployment = Deployment(args.root, args.env_file, args.project, args.gateway_port, args.backend_port, args.host)
        source = PostgresClient(['runuser', '-u', 'postgres', '--'], 'postgres', 'blog')
        report = NativeCutover(deployment, NativeHost(), source).apply(args.artifacts, args.commit)
        print(json.dumps(report, sort_keys=True))
    except (ArtifactError, DatabaseError, DeployError, CutoverError, OSError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, CutoverError): raise SystemExit(str(error)) from None
        raise SystemExit('First cutover stopped. Inspect the protected migration journal; production credentials were not printed') from None
