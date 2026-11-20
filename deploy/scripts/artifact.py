"""Deterministic, bounded release packages for the Compose monorepo."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

ROOTS = ('backend/app/', 'backend/alembic/', 'frontend-web/dist/', 'frontend-admin/dist/',
         'deploy/docker/', 'deploy/nginx/', 'deploy/scripts/')
FILES = ('backend/alembic.ini', 'backend/requirements.txt', '.env.example', 'docker-compose.yml')
REQUIRED = ('backend/app/main.py', 'backend/alembic/env.py', 'backend/alembic.ini', 'backend/requirements.txt',
            'frontend-web/dist/index.html', 'frontend-admin/dist/index.html',
            'deploy/docker/docker-compose.yml', 'deploy/scripts/deploy.sh')
MAX_FILE = 50 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
MAX_FILES = 5000


class ArtifactError(ValueError):
    pass


def commit_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{40}', value):
        raise ArtifactError('A full source commit is required')
    return value


def allowed_path(name):
    path = PurePosixPath(name)
    if (not name or len(name) > 500 or '\\' in name or path.is_absolute() or
            any(part in ('', '.', '..') for part in name.split('/')) or
            any(ord(char) < 32 for char in name)):
        raise ArtifactError('Unsafe package member path')
    if name not in FILES and not any(name.startswith(prefix) for prefix in ROOTS):
        raise ArtifactError('Unexpected package member')
    if (path.name.startswith('.env') and path.name != '.env.example') or path.suffix.lower() in ('.key', '.pem', '.p12', '.sqlite', '.db', '.log'):
        raise ArtifactError('Credential or runtime-data file is not a release input')
    if any(part in ('.git', '.local', '.venv', 'venv', 'node_modules', '__pycache__') for part in path.parts):
        raise ArtifactError('Unexpected runtime or dependency directory')
    return path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(root, commit, output=None):
    root = Path(root).resolve()
    commit_id(commit)
    output = Path(output) if output else root / 'artifacts'
    if output.is_symlink():
        raise ArtifactError('Unexpected artifact output directory')
    output = output.resolve()
    inputs = []
    for name in (*ROOTS, *FILES):
        path = root / name.rstrip('/')
        if not path.exists() or path.is_symlink():
            raise ArtifactError('Release input is missing or linked')
        for item in sorted(path.rglob('*')) if path.is_dir() else (path,):
            if item.is_symlink():
                raise ArtifactError('Linked release input')
            if '__pycache__' in item.parts:
                continue
            if item.is_file():
                relative = item.relative_to(root).as_posix()
                allowed_path(relative)
                if item.stat().st_size > MAX_FILE:
                    raise ArtifactError('Release file exceeds limit')
                inputs.append((relative, item))
    names = {name for name, _ in inputs}
    if len(inputs) != len(names) or not set(REQUIRED) <= names or len(inputs) > MAX_FILES:
        raise ArtifactError('Release inputs are incomplete or duplicated')
    if sum(path.stat().st_size for _, path in inputs) > MAX_TOTAL:
        raise ArtifactError('Release inputs exceed limit')
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ArtifactError('Unexpected artifact output directory')
    archive = output / ('blog-' + commit + '.tar.gz')
    with archive.open('wb') as file:
        with gzip.GzipFile(filename='', mode='wb', fileobj=file, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as tar:
                for name, source in sorted(inputs):
                    member = tarfile.TarInfo(name)
                    member.size = source.stat().st_size
                    member.mode = 0o755 if name.endswith('.sh') else 0o644
                    member.mtime = 0
                    with source.open('rb') as stream:
                        tar.addfile(member, stream)
    sha = digest(archive)
    archive.with_suffix('.gz.sha256').write_text(sha + '  ' + archive.name + '\n', encoding='utf-8')
    manifest = {'format': 2, 'stack': 'compose', 'commit': commit, 'archive': archive.name,
                'sha256': sha, 'entrypoint': 'deploy/scripts/deploy.sh', 'schema_revision': '0003'}
    (output / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n', encoding='utf-8')
    verify(output, commit)
    return output


def verify(directory, commit):
    directory = Path(directory).resolve()
    commit_id(commit)
    path = directory / 'manifest.json'
    if path.is_symlink() or path.stat().st_size > 16 * 1024:
        raise ArtifactError('Invalid manifest file')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict):
        raise ArtifactError('Manifest must be an object')
    expected = {'format': 2, 'stack': 'compose', 'commit': commit,
                'archive': 'blog-' + commit + '.tar.gz', 'entrypoint': 'deploy/scripts/deploy.sh', 'schema_revision': '0003'}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ArtifactError('Manifest does not match expected source and format')
    if not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get('sha256', ''))):
        raise ArtifactError('Invalid artifact digest')
    archive = directory / manifest['archive']
    if archive.is_symlink() or archive.stat().st_size > MAX_TOTAL or digest(archive) != manifest['sha256']:
        raise ArtifactError('Artifact digest or size mismatch')
    checksum = directory / (archive.name + '.sha256')
    if checksum.is_symlink() or checksum.stat().st_size > 4096:
        raise ArtifactError('Invalid checksum file')
    if checksum.read_text().strip() != manifest['sha256'] + '  ' + archive.name:
        raise ArtifactError('Checksum file mismatch')
    found, total = set(), 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            allowed_path(member.name)
            if not member.isfile() or member.name in found or member.size < 0 or member.size > MAX_FILE:
                raise ArtifactError('Unsupported, duplicate or oversized package member')
            found.add(member.name); total += member.size
            if len(found) > MAX_FILES or total > MAX_TOTAL:
                raise ArtifactError('Unpacked release exceeds limits')
    if not set(REQUIRED) <= found:
        raise ArtifactError('Release package is incomplete')
    return manifest


def extract(directory, commit, destination):
    manifest = verify(directory, commit)
    destination = Path(destination)
    if destination.exists():
        raise ArtifactError('Extraction destination must be new')
    destination.mkdir(parents=True, mode=0o750)
    destination = destination.resolve()
    with tarfile.open(Path(directory) / manifest['archive'], 'r:gz') as tar:
        for member in tar:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(destination):
                raise ArtifactError('Extraction escaped destination')
            with tar.extractfile(member) as source, target.open('xb') as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            target.chmod(0o755 if member.name.endswith('.sh') else 0o644)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('package', 'verify', 'extract'))
    parser.add_argument('--commit', required=True)
    parser.add_argument('--root', default='.')
    parser.add_argument('--artifacts', default='artifacts')
    parser.add_argument('--destination')
    args = parser.parse_args()
    if args.action == 'package':
        package(args.root, args.commit, args.artifacts)
    elif args.action == 'verify':
        verify(args.artifacts, args.commit)
    else:
        if not args.destination:
            parser.error('--destination is required for extraction')
        extract(args.artifacts, args.commit, args.destination)
    print('Release artifact ' + args.action + ': verified for ' + args.commit)


if __name__ == '__main__':
    try:
        main()
    except (ArtifactError, OSError, ValueError, tarfile.TarError):
        raise SystemExit('Release artifact validation did not complete; no deployment was started.') from None
