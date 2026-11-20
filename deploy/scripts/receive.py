"""Receive a source-bound format 2 Flow archive; never initializes a production DB."""
import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from artifact import ArtifactError, MAX_TOTAL, commit_id, extract, verify


@contextlib.contextmanager
def unpack(archive, commit, work_parent=None):
    commit_id(commit)
    archive = Path(archive).absolute()
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_TOTAL + 1024 * 1024:
        raise ArtifactError('Invalid Flow download')
    expected = {'artifacts/manifest.json': 16384,
                'artifacts/blog-' + commit + '.tar.gz': MAX_TOTAL,
                'artifacts/blog-' + commit + '.tar.gz.sha256': 4096}
    with tempfile.TemporaryDirectory(prefix='blog-flow-v2-', dir=work_parent) as temporary:
        work = Path(temporary)
        (work / 'artifacts').mkdir(mode=0o700)
        found, total = set(), 0
        with tarfile.open(archive, 'r:*') as tar:
            for member in tar:
                name = member.name
                while name.startswith('./'): name = name[2:]
                if member.isdir() and name in ('', '.', 'artifacts'):
                    continue
                if (name not in expected or name in found or not member.isfile() or '\\' in name or
                        member.size < 0 or member.size > expected.get(name, 0)):
                    raise ArtifactError('Unexpected Flow archive member')
                total += member.size
                if total > MAX_TOTAL + 20480:
                    raise ArtifactError('Flow archive exceeds limits')
                found.add(name)
                destination = work.joinpath(*PurePosixPath(name).parts)
                with destination.open('xb') as output, tar.extractfile(member) as source:
                    shutil.copyfileobj(source, output)
                destination.chmod(0o600)
        if found != set(expected):
            raise ArtifactError('Include the artifacts/ directory when uploading to Packages')
        verify(work / 'artifacts', commit)
        yield work


def receive(archive, commit, *, verify_only=False, root='/opt/blog-fullstack',
            env_file='/opt/blog-fullstack/shared/runtime.env', project='blog-production-v2',
            gateway_port=18080, backend_port=18000, host='kongqi.xyz', work_parent=None):
    with unpack(archive, commit, work_parent) as work:
        if verify_only:
            return {'verified': True, 'format': 2, 'commit': commit}
        root = Path(root).absolute()
        ready = root / 'shared/traffic-ready.json'
        if ready.is_symlink() or not ready.is_file() or ready.stat().st_size > 4096:
            raise ArtifactError('Complete and verify the first data migration and Nginx cutover before enabling Flow deployment')
        if json.loads(ready.read_text()) != {'project': project, 'gateway_port': gateway_port, 'host': host}:
            raise ArtifactError('Active production traffic does not match this deployment target')
        extract(work / 'artifacts', commit, work / 'source')
        subprocess.run(['bash', str(work / 'source/deploy/scripts/deploy.sh'),
                        '--artifacts', str(work / 'artifacts'), '--commit', commit,
                        '--root', str(root), '--env-file', str(env_file), '--project', project,
                        '--gateway-port', str(gateway_port), '--backend-port', str(backend_port), '--host', host],
                       check=True, timeout=3600)
        return {'deployed': True, 'format': 2, 'commit': commit}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--commit', default=os.getenv('COMMIT_SHA'), required=not bool(os.getenv('COMMIT_SHA')))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(receive(args.archive, args.commit, verify_only=args.verify_only), sort_keys=True))
    except (ArtifactError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError):
        raise SystemExit('Flow artifact processing stopped; no unverified code was executed.') from None
