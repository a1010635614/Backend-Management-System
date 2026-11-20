"""Restore one backup in a disposable, network-isolated PostgreSQL container."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time

from database_tools import DatabaseError, PostgresClient, file_digest, write_json

DEFAULT_IMAGE = 'public.ecr.aws/docker/library/postgres:16.15-bookworm'


def metadata_for(archive):
    path = Path(archive).absolute()
    record = path.with_suffix('.dump.json')
    if path.resolve() != path or path.is_symlink() or record.is_symlink() or record.stat().st_size > 16384:
        raise DatabaseError('Invalid backup or metadata path')
    metadata = json.loads(record.read_text())
    if (not isinstance(metadata, dict) or metadata.get('format') != 1 or metadata.get('archive') != path.name or
            not re.fullmatch('[a-f0-9]{64}', str(metadata.get('sha256', ''))) or
            type(metadata.get('bytes')) is not int or metadata['bytes'] != path.stat().st_size or
            metadata.get('schema') not in (None, '0001', '0002', '0003') or
            file_digest(path) != metadata['sha256']):
        raise DatabaseError('Backup and metadata do not match')
    return metadata


class DisposablePostgres:
    def __init__(self, workspace, image=DEFAULT_IMAGE):
        self.base = Path(workspace).absolute()
        if self.base.resolve() != self.base or ',' in str(self.base) or self.base == Path('/'):
            raise DatabaseError('Invalid restore workspace')
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.base.stat().st_uid != os.getuid() or self.base.stat().st_mode & 0o022:
            raise DatabaseError('Restore workspace is not protected')
        if not re.fullmatch(r'[a-z0-9][a-z0-9/:._@-]+', image):
            raise DatabaseError('Invalid PostgreSQL image name')
        self.image, self.identifier = image, secrets.token_hex(12)
        self.name, self.work, self.started = 'blog-restore-' + self.identifier, None, False
        self.attempted = False

    def __enter__(self):
        self.work = Path(tempfile.mkdtemp(prefix='.restore-', dir=self.base))
        data = self.work / 'data'; data.mkdir(mode=0o700)
        environment = self.work / 'postgres.env'
        fd = os.open(environment, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('POSTGRES_USER=restore_user\nPOSTGRES_DB=restorecheck\nPOSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n')
        try:
            self.attempted = True
            result = subprocess.run(['docker', 'run', '-d', '--pull', 'never', '--name', self.name,
                '--label', 'blog.restore.id=' + self.identifier, '--network', 'none',
                '--memory', '192m', '--memory-swap', '256m', '--pids-limit', '64',
                '--security-opt', 'no-new-privileges', '--env-file', str(environment),
                '--mount', 'type=bind,src=' + str(data) + ',dst=/var/lib/postgresql/data',
                self.image, 'postgres', '-c', 'shared_buffers=16MB', '-c', 'max_connections=10',
                '-c', 'work_mem=1MB', '-c', 'maintenance_work_mem=16MB', '-c', 'timezone=UTC'],
                capture_output=True, timeout=90)
            if result.returncode: raise DatabaseError('Disposable PostgreSQL could not be created')
            self.started = True
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                result = subprocess.run(['docker', 'exec', self.name, 'pg_isready', '-U', 'restore_user', '-d', 'restorecheck'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if result.returncode == 0:
                    return PostgresClient(['docker', 'exec', '-i', self.name], 'restore_user', 'restorecheck')
                time.sleep(.5)
            raise DatabaseError('Disposable PostgreSQL did not become ready')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *unused):
        if self.attempted:
            result = subprocess.run(['docker', 'inspect', '--format', '{{index .Config.Labels "blog.restore.id"}}', self.name],
                                    capture_output=True, timeout=10)
            if result.returncode:
                absent = subprocess.run(['docker', 'ps', '-a', '--filter', 'label=blog.restore.id=' + self.identifier,
                                         '--format', '{{.ID}}'], capture_output=True, timeout=10)
                if absent.returncode or absent.stdout.strip():
                    raise DatabaseError('Restore container state is uncertain; temporary directory was retained')
            else:
                if result.stdout.decode().strip() != self.identifier:
                    raise DatabaseError('Restore container identity differs; temporary directory was retained')
                result = subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True, timeout=30)
                if result.returncode:
                    raise DatabaseError('Restore container cleanup failed; temporary directory was retained')
            self.started = False
            self.attempted = False
        if self.work is not None:
            path = self.work
            if path.resolve() != path or path.parent != self.base or not path.name.startswith('.restore-'):
                raise DatabaseError('Unexpected restore cleanup path')
            shutil.rmtree(path)
            self.work = None


def verify_restore(archive, workspace, *, image=DEFAULT_IMAGE, expected=None):
    archive = Path(archive).absolute()
    metadata = metadata_for(archive)
    with DisposablePostgres(workspace, image) as target:
        fingerprint = target.restore_empty(archive, metadata)
        if expected is not None and fingerprint != expected:
            raise DatabaseError('Restored rows differ from the frozen source database')
    record = {'format': 1, 'archive': archive.name, 'sha256': metadata['sha256'], 'schema': metadata['schema'],
              'verified_at': datetime.now(timezone.utc).isoformat(), 'fingerprint': fingerprint,
              'source_compared': expected is not None, 'isolated_restore': True}
    write_json(archive.with_suffix('.dump.restore.json'), record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--workspace', default='/opt/blog-fullstack/backups')
    parser.add_argument('--image', default=DEFAULT_IMAGE)
    args = parser.parse_args()
    try:
        report = verify_restore(args.archive, args.workspace, image=args.image)
        print(json.dumps({'restore': 'passed', 'schema': report['schema'],
                          'counts': {table: row['count'] for table, row in report['fingerprint'].items()}}, sort_keys=True))
    except (DatabaseError, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('Isolated backup restore was not verified; no production database was overwritten.') from None
