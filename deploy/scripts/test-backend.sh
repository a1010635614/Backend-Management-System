#!/usr/bin/env bash
# Real, disposable PostgreSQL + Redis tests; never falls back to production URLs.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python="${CI_PYTHON_BIN:-python3}"
# Preserve a virtualenv's Python symlink; dereferencing it loses site-packages.
if [[ "$python" == */* ]]; then python=$(realpath -s "$python"); else python=$(command -v "$python"); fi
if [[ -n "${POSTGRES_BIN:-}" ]]; then postgres_bin="$POSTGRES_BIN"; else postgres_bin=$(dirname "$(command -v initdb)"); fi
redis_server="${REDIS_SERVER_BIN:-$(command -v redis-server)}"
test -x "$postgres_bin/initdb"
test -x "$postgres_bin/pg_ctl"
test -x "$redis_server"
work=$(mktemp -d /tmp/blog-integration.XXXXXXXX)
run_as=()
if [[ $(id -u) == 0 ]]; then
  chown postgres:postgres "$work"
  run_as=(runuser -u postgres --)
fi
pg_started=false
redis_pid=''
cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$redis_pid" ]]; then kill "$redis_pid" 2>/dev/null || true; wait "$redis_pid" 2>/dev/null || true; fi
  if "$pg_started"; then "${run_as[@]}" "$postgres_bin/pg_ctl" -D "$work/postgres" -m fast -w stop >/dev/null 2>&1 || true; fi
  if [[ "$(realpath "$work")" == "$work" && "$work" == /tmp/blog-integration.* ]]; then rm -rf -- "$work"; fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
read -r pg_port redis_port < <("$python" - <<'PY'
import socket
sockets=[]
try:
    for _ in range(2):
        s=socket.socket(); s.bind(('127.0.0.1',0)); sockets.append(s)
    print(*(s.getsockname()[1] for s in sockets))
finally:
    for s in sockets: s.close()
PY
)
"${run_as[@]}" "$postgres_bin/initdb" -D "$work/postgres" -U blog_test -A trust --no-locale --encoding=UTF8 >/dev/null
"${run_as[@]}" "$postgres_bin/pg_ctl" -D "$work/postgres" -l "$work/postgres.log" -w start \
  -o "-h 127.0.0.1 -p $pg_port -k $work -c shared_buffers=16MB -c max_connections=25 -c fsync=off -c full_page_writes=off -c timezone=UTC" >/dev/null
pg_started=true
"${run_as[@]}" "$postgres_bin/createdb" -h 127.0.0.1 -p "$pg_port" -U blog_test blogtest
"${run_as[@]}" "$postgres_bin/createdb" -h 127.0.0.1 -p "$pg_port" -U blog_test upgradecheck
"${run_as[@]}" "$postgres_bin/createdb" -h 127.0.0.1 -p "$pg_port" -U blog_test backupsource
"${run_as[@]}" "$postgres_bin/createdb" -h 127.0.0.1 -p "$pg_port" -U blog_test backuprestore
"${run_as[@]}" "$redis_server" --bind 127.0.0.1 --port "$redis_port" --save '' --appendonly no \
  --maxmemory 64mb --maxmemory-policy noeviction --dir "$work" >"$work/redis.log" 2>&1 &
redis_pid=$!
export TEST_DATABASE_URL="postgresql+asyncpg://blog_test@127.0.0.1:$pg_port/blogtest"
export UPGRADE_DATABASE_URL="postgresql+asyncpg://blog_test@127.0.0.1:$pg_port/upgradecheck"
export BACKUP_DATABASE_URL="postgresql+asyncpg://blog_test@127.0.0.1:$pg_port/backupsource"
export RESTORE_DATABASE_URL="postgresql+asyncpg://blog_test@127.0.0.1:$pg_port/backuprestore"
export POSTGRES_BIN="$postgres_bin"
export TEST_REDIS_URL="redis://127.0.0.1:$redis_port/15"
export DATABASE_URL="$TEST_DATABASE_URL" REDIS_URL="$TEST_REDIS_URL" APP_ENV=test BLOG_TEST_ISOLATED=1
export JWT_SECRET=test-only-isolated-signing-key-with-48-characters
export ADMIN_EMAILS=admin@example.com
"$python" - <<'PY'
import os,time
from redis import Redis
cache=Redis.from_url(os.environ['TEST_REDIS_URL'],socket_timeout=1)
for attempt in range(30):
    try:
        assert cache.ping()
        print('Disposable Redis: '+cache.info('server')['redis_version'],flush=True)
        break
    except Exception:
        if attempt==29: raise
        time.sleep(.1)
cache.close()
PY
cd "$repo/backend"
"$python" -m alembic upgrade head
"$python" -m alembic check
"$python" -m pytest "$@"
