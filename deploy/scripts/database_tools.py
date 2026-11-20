"""Bounded PostgreSQL dump/restore operations; credentials never appear in arguments."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

TABLE_KEYS = {'users': 'id', 'posts': 'id', 'assets': 'id', 'analytics_events': 'id',
              'email_codes': 'id', 'alembic_version': 'version_num'}


class DatabaseError(RuntimeError):
    pass


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.database-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, sort_keys=True); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def deployment_lock(root):
    import fcntl
    root = Path(root).absolute()
    if root.resolve() != root or root.is_symlink() or root == Path('/'):
        raise DatabaseError('Unexpected deployment lock directory')
    path = root / '.deploy.lock'
    if path.is_symlink(): raise DatabaseError('Unexpected deployment lock file')
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise DatabaseError('Another deployment or backup is running') from None
        yield


class PostgresClient:
    def __init__(self, prefix, user, database, *, bin_dir='', host=None, port=None, environment=None):
        if not all(re.fullmatch(r'[a-z][a-z0-9_]{0,62}', item) for item in (user, database)):
            raise DatabaseError('Invalid PostgreSQL user or database name')
        self.prefix, self.bin_dir = list(prefix), bin_dir
        self.environment = environment
        self.connection = ['-U', user, '-d', database]
        if host is not None:
            if host not in ('127.0.0.1', 'localhost') or port is None or not 1024 <= int(port) <= 65535:
                raise DatabaseError('Use an explicit loopback test port')
            self.connection += ['-h', host, '-p', str(port)]

    def command(self, binary, *args):
        return [*self.prefix, str(Path(self.bin_dir) / binary) if self.bin_dir else binary, *args]

    def query(self, sql):
        result = subprocess.run(self.command('psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', *self.connection),
                                input=sql.encode(), capture_output=True, timeout=60, env=self.environment)
        if result.returncode:
            raise DatabaseError('PostgreSQL query failed; data and connection details were not printed')
        return result.stdout.decode().strip()

    def revision(self):
        if self.query("SELECT to_regclass('public.alembic_version');") == '':
            if self.query("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';") == '0':
                return None
            raise DatabaseError('An application schema marker is missing')
        value = self.query('SELECT version_num FROM public.alembic_version;')
        if value not in ('0001', '0002', '0003'):
            raise DatabaseError('Unexpected schema revision')
        return value

    def fingerprint(self, *, legacy_data=False):
        """Stream canonical rows; never collect or print business records."""
        revision = self.revision()
        if revision is None: return {}
        result = {}
        for table, key in TABLE_KEYS.items():
            if revision == '0001' and table == 'assets': continue
            if legacy_data and table == 'alembic_version': continue
            projection = 'to_jsonb(t)'
            if legacy_data and table == 'users':
                projection += " - ARRAY['role','is_active']"
            elif legacy_data and table == 'posts':
                projection += " - ARRAY['status','author_id','updated_at']"
            sql = ("SET timezone='UTC'; SET statement_timeout='60s'; SET lock_timeout='10s'; "
                   f'COPY (SELECT ({projection})::text FROM public."{table}" t ORDER BY "{key}") TO STDOUT;')
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(self.command('psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                    *self.connection, '-c', sql), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=errors, env=self.environment)
                timer = threading.Timer(65, process.kill)
                timer.daemon = True; timer.start()
                digest, count = hashlib.sha256(), 0
                try:
                    while line := process.stdout.readline(2 * 1024 * 1024 + 1):
                        if len(line) > 2 * 1024 * 1024:
                            raise DatabaseError('A database row exceeds the verification limit')
                        digest.update(line); count += 1
                    if process.wait(timeout=5):
                        raise DatabaseError('Database fingerprint could not be completed')
                finally:
                    timer.cancel()
                    process.stdout.close()
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            result[table] = {'count': count, 'sha256': digest.hexdigest()}
        return result

    def dump(self, destination, *, source_commit=None):
        path = Path(destination)
        if path.is_symlink(): raise DatabaseError('Invalid backup path')
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                result = subprocess.run(self.command('pg_dump', *self.connection, '--format=custom',
                    '--no-owner', '--no-privileges'), stdout=stream, stderr=subprocess.PIPE,
                    timeout=300, env=self.environment)
                if result.returncode: raise DatabaseError('Database backup did not complete')
                stream.flush(); os.fsync(stream.fileno())
            self.validate_dump(path)
            metadata = {'format': 1, 'archive': path.name, 'sha256': file_digest(path), 'bytes': path.stat().st_size,
                        'created_at': datetime.now(timezone.utc).isoformat(), 'schema': self.revision(),
                        'source_commit': source_commit}
            write_json(path.with_suffix('.dump.json'), metadata)
            return metadata
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def validate_dump(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size < 100:
            raise DatabaseError('Invalid PostgreSQL archive')
        with path.open('rb') as stream:
            if stream.read(5) != b'PGDMP': raise DatabaseError('Expected a custom PostgreSQL dump')
        # A buffered seek can leave the inherited OS descriptor past the header.
        # Give pg_restore a newly opened descriptor at the actual file beginning.
        with path.open('rb') as stream:
            result = subprocess.run(self.command('pg_restore', '--list'), stdin=stream,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30, env=self.environment)
        if result.returncode: raise DatabaseError('PostgreSQL archive table of contents is invalid')

    def restore_empty(self, archive, metadata):
        path = Path(archive)
        self.validate_dump(path)
        if (path.name != metadata.get('archive') or path.stat().st_size != metadata.get('bytes') or
                file_digest(path) != metadata.get('sha256')):
            raise DatabaseError('Backup does not match its recorded digest')
        if self.query("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';") != '0':
            raise DatabaseError('Restore target is not empty; nothing was overwritten')
        with path.open('rb') as stream:
            result = subprocess.run(self.command('pg_restore', *self.connection, '--exit-on-error',
                '--single-transaction', '--no-owner', '--no-privileges'), stdin=stream,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300, env=self.environment)
        if result.returncode: raise DatabaseError('Restore did not complete; target transaction was rolled back')
        if self.revision() != metadata.get('schema'):
            raise DatabaseError('Restored schema does not match the backup')
        return self.fingerprint()
