#!/usr/bin/env bash
# Linux Flow runner: Node.js 20+, Python 3.12, Docker Compose for PostgreSQL checks.
set -euo pipefail
: "${COMMIT_SHA:?Map the source commit SHA from Flow}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
POSTGRES_TEST_IMAGE=postgres:16-alpine bash deploy/test-postgres.sh
(cd frontend && npm ci && npm run build)
mkdir -p artifacts
python3 - <<'PY'
import hashlib,json,os,tarfile
from pathlib import Path
sha=os.environ['COMMIT_SHA']
output=Path('artifacts')/('blog-'+sha+'.tar.gz')
with tarfile.open(output,'w:gz') as tar:
    for name in ('backend/app','backend/migrations','backend/tests','backend/alembic.ini','backend/requirements.txt','frontend/dist'):
        root=Path(name)
        for path in (root.rglob('*') if root.is_dir() else [root]):
            if path.is_file() and '__pycache__' not in path.parts:
                tar.add(path,arcname=path.as_posix())
digest=hashlib.file_digest(output.open('rb'),'sha256').hexdigest()
output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n')
Path('artifacts/manifest.json').write_text(json.dumps({'commit':sha,'archive':output.name,'sha256':digest}))
PY
