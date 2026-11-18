#!/usr/bin/env bash
# Upload the matching archive and .sha256 file to /opt/vueblog/incoming beforehand.
set -euo pipefail
: "${COMMIT_SHA:?}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
exec 9>/opt/vueblog/.native-release.lock
flock -n 9 || { echo 'Another release is running'; exit 1; }
cd /opt/vueblog/incoming
sha256sum --check "blog-$COMMIT_SHA.tar.gz.sha256"
release="/opt/vueblog/releases/$COMMIT_SHA"
test ! -e "$release" || { echo 'Release path already exists; choose a new commit'; exit 1; }
previous=$(readlink -f /opt/vueblog/current)
test -n "$previous" && test -d "$previous"
case "$previous" in /opt/vueblog/releases/*) ;; *) exit 2 ;; esac
/usr/local/sbin/vueblog-backup
mkdir -p "$release"
# Reject path traversal, links, devices and unexpected directories before extraction.
python3 - "$COMMIT_SHA" "$release" <<'PY'
from pathlib import PurePosixPath
import sys,tarfile
with tarfile.open('blog-'+sys.argv[1]+'.tar.gz') as tar:
    for member in tar.getmembers():
        path=PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not member.isfile() or path.parts[0] not in ('backend','frontend'):
            raise SystemExit('Unsafe artifact member')
    tar.extractall(sys.argv[2],filter='data')
PY
chown -R blog:blog "$release"
chmod 755 "$release" "$release/frontend"
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install --disable-pip-version-check --no-cache-dir -q -r "$release/backend/requirements.txt"
cd "$release/backend"
"$release/.venv/bin/python" -m unittest discover -s tests -v
# Run schema changes once, without shell-expanding secret values.
"$release/.venv/bin/python" - <<'PY'
import os,subprocess,sys
from dotenv import dotenv_values
env={**os.environ,**{k:v for k,v in dotenv_values('/etc/vueblog.env',interpolate=False).items() if v is not None}}
for args in (['upgrade','head'],['check']):
    subprocess.run([sys.executable,'-m','alembic',*args],env=env,check=True)
PY
unit=/etc/systemd/system/vueblog.service
cp -p "$unit" "$release/previous.service"
rollback() {
    cp -p "$release/previous.service" "$unit"
    ln -sfn "$previous" /opt/vueblog/.current-rollback
    mv -Tf /opt/vueblog/.current-rollback /opt/vueblog/current
    systemctl daemon-reload
    systemctl restart vueblog
    echo 'Release failed; previous code/service restored. Schema was not downgraded.'
}
trap rollback ERR
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/systemd/system/vueblog.service')
s=p.read_text()
expected='ExecStart=/opt/vueblog/venv/bin/python '
replacement='ExecStart=/opt/vueblog/current/.venv/bin/python '
if expected not in s and replacement not in s: raise SystemExit('Unexpected service command')
p.write_text(s.replace(expected,replacement))
PY
ln -sfn "$release" /opt/vueblog/.current-next
mv -Tf /opt/vueblog/.current-next /opt/vueblog/current
systemctl daemon-reload
systemctl restart vueblog
healthy=false
for retry in $(seq 1 20); do
    if curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:8000/api/health >/dev/null; then healthy=true; break; fi
    sleep 1
done
"$healthy"
curl -fsS --connect-timeout 3 --max-time 10 --resolve kongqi.xyz:443:127.0.0.1 https://kongqi.xyz/ >/dev/null
printf '%s\n' "$COMMIT_SHA" > /opt/vueblog/.current-release
trap - ERR
echo 'Release health checks passed.'
