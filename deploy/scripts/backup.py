"""Production Compose backup with optional isolated restore and verified retention."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from database_tools import DatabaseError, deployment_lock
from deploy_release import Deployment, DeployError
from restore_drill import metadata_for, verify_restore, DEFAULT_IMAGE


def prune_verified(directory, days=7, *, now=None):
    if not 1 <= days <= 90: raise DatabaseError('Retention must be 1 to 90 days')
    directory = Path(directory).absolute()
    if directory.resolve() != directory or directory.is_symlink():
        raise DatabaseError('Unexpected backup retention directory')
    valid = []
    for path in directory.glob('blog-*.dump'):
        if not re.fullmatch(r'blog-\d{8}T\d{6}(?:\d{6})?Z-[a-f0-9]{12}\.dump', path.name): continue
        files = [path, path.with_suffix('.dump.json'), path.with_suffix('.dump.restore.json'), path.with_suffix('.dump.sha256')]
        if any(not item.is_file() or item.is_symlink() or item.stat().st_uid != os.getuid() for item in files): continue
        if files[2].stat().st_size > 32768: continue
        try:
            metadata = metadata_for(path)
            checked = json.loads(files[2].read_text())
            if not isinstance(checked, dict) or checked.get('sha256') != metadata['sha256'] or checked.get('isolated_restore') is not True: continue
        except (DatabaseError, OSError, ValueError): continue
        valid.append((path.stat().st_mtime, files))
    valid.sort(reverse=True)
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).timestamp()
    removed = 0
    # Preserve at least two verified restore points, even if the daily job stopped.
    for stamp, files in valid[2:]:
        if stamp >= cutoff: continue
        for path in files: path.unlink()
        removed += 1
    return removed


def run_backup(deployment, *, drill=False, retention=7, image=DEFAULT_IMAGE):
    with deployment_lock(deployment.root):
        release = deployment.previous()
        if release is None: raise DeployError('A verified Compose release is required before daily backups')
        archive = deployment.backup(release)
        result = {'archive': archive.name, 'backup': 'passed', 'restore': 'not-run'}
        if drill:
            record = verify_restore(archive, deployment.backups, image=image)
            result.update(restore='passed', schema=record['schema'],
                          counts={table: row['count'] for table, row in record['fingerprint'].items()})
        result['expired_verified_backups_removed'] = prune_verified(deployment.backups, retention)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/opt/blog-fullstack')
    parser.add_argument('--env-file', default='/opt/blog-fullstack/shared/runtime.env')
    parser.add_argument('--project', default='blog-production-v2')
    parser.add_argument('--gateway-port', type=int, default=18080)
    parser.add_argument('--backend-port', type=int, default=18000)
    parser.add_argument('--host', default='kongqi.xyz')
    parser.add_argument('--retention-days', type=int, default=7)
    parser.add_argument('--drill', action='store_true')
    parser.add_argument('--image', default=DEFAULT_IMAGE)
    args = parser.parse_args()
    try:
        deployment = Deployment(args.root, args.env_file, args.project, args.gateway_port, args.backend_port, args.host)
        print(json.dumps(run_backup(deployment, drill=args.drill, retention=args.retention_days, image=args.image), sort_keys=True))
    except (DatabaseError, DeployError, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('Backup/restore verification did not complete; production data was not replaced.') from None
