"""Upload a test-only source bundle, run isolated PG checks, never switch current."""
from pathlib import Path
import secrets
import subprocess
import tarfile
from remote import ROOT,ssh_arguments

tag='check-'+secrets.token_hex(8)
archive=ROOT/'.local'/f'{tag}.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for name in ('backend/app','backend/migrations','backend/tests','backend/alembic.ini'):
        path=ROOT/name
        for file in (path.rglob('*') if path.is_dir() else [path]):
            if file.is_file() and '__pycache__' not in file.parts:
                tar.add(file,arcname=file.relative_to(ROOT).as_posix())
command=f'mkdir -p /opt/vueblog/verification/{tag} && tar -xzf - -C /opt/vueblog/verification/{tag}'
with archive.open('rb') as file:
    subprocess.run(ssh_arguments()+[command],stdin=file,check=True)
script=(ROOT/'deploy/verify-postgres-native.sh').read_text(encoding='utf-8')
script=script.replace('cd /opt/vueblog/current/backend',f'cd /opt/vueblog/verification/{tag}/backend')
subprocess.run(ssh_arguments()+['bash -se'],input=script.encode(),check=True)
print('Staged PostgreSQL checks passed; current service and business database were not changed.')
