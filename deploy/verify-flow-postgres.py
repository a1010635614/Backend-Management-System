"""Verify the Flow PostgreSQL script in a fresh cluster without touching production data."""
import secrets
import subprocess
import tarfile
from remote import ROOT, ssh_arguments

tag = 'flow-pg-check-' + secrets.token_hex(8)
archive = ROOT / '.local' / (tag + '.tar.gz')
archive.parent.mkdir(exist_ok=True)
with tarfile.open(archive, 'w:gz') as package:
    for name in ('backend/app', 'backend/migrations', 'backend/tests', 'backend/alembic.ini'):
        path = ROOT / name
        for file in (path.rglob('*') if path.is_dir() else (path,)):
            if file.is_file() and '__pycache__' not in file.parts:
                package.add(file, arcname=file.relative_to(ROOT).as_posix())
target = '/opt/vueblog/verification/' + tag
with archive.open('rb') as source:
    subprocess.run(ssh_arguments() + ['mkdir -p ' + target + ' && tar -xzf - -C ' + target], stdin=source, check=True)
prefix = """set -euo pipefail
/usr/bin/python3 - <<'PY'
from pathlib import Path
values = {line.split(':',1)[0]: line.split(':',1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines()}
available = int(values['MemAvailable'].split()[0]) // 1024
print('Available memory before isolated cluster check (MiB):', available)
if available < 256:
    raise SystemExit('Insufficient headroom for an additional test cluster; production was not changed')
PY
export CI_PYTHON_BIN=/opt/vueblog/venv/bin/python
cd TARGET/backend
""".replace('TARGET', target)
script = prefix + (ROOT / 'deploy/test-flow-postgres.sh').read_text(encoding='utf-8')
subprocess.run(ssh_arguments() + ['bash -se'], input=script.encode(), check=True)
print('Fresh-cluster Flow PostgreSQL script verified; the production database and current release were not changed.')
