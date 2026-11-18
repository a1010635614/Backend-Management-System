#!/usr/bin/env bash
# Run against a disposable local PostgreSQL 16 cluster inside the CI image.
set -euo pipefail
ci_python="${CI_PYTHON_BIN:-python3}"
pg_check_bin="${PG_CHECK_BIN:-/usr/lib/postgresql/16/bin}"
[[ "$("$pg_check_bin/postgres" --version)" == *' 16.'* ]] || { echo 'PostgreSQL 16 is required'; exit 2; }
pg_check_dir=$(mktemp -d /tmp/vueblog-pgcheck.XXXXXXXX)
cleanup() {
    result=$?
    trap - EXIT
    if [[ -d "$pg_check_dir/data" ]]; then
        runuser -u postgres -- "$pg_check_bin/pg_ctl" -D "$pg_check_dir/data" -m fast -w stop >/dev/null 2>&1 || true
    fi
    if ((result)) && [[ -f "$pg_check_dir/server.log" ]]; then tail -n 60 "$pg_check_dir/server.log"; fi
    case "$pg_check_dir" in /tmp/vueblog-pgcheck.*) rm -rf -- "$pg_check_dir";; esac
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
chown postgres:postgres "$pg_check_dir"
pg_check_port=$("$ci_python" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
runuser -u postgres -- "$pg_check_bin/initdb" -D "$pg_check_dir/data" --username=blog_ci --auth=trust --no-locale --encoding=UTF8 >/dev/null
runuser -u postgres -- "$pg_check_bin/pg_ctl" -D "$pg_check_dir/data" \
    -o "-h 127.0.0.1 -p $pg_check_port -k $pg_check_dir -c fsync=off" -l "$pg_check_dir/server.log" -w start
"$pg_check_bin/createdb" -h 127.0.0.1 -p "$pg_check_port" -U blog_ci blog_ci
pg_check_version=$("$pg_check_bin/psql" -h 127.0.0.1 -p "$pg_check_port" -U blog_ci -d blog_ci -Atc 'SHOW server_version_num')
[[ "$pg_check_version" =~ ^16[0-9]{4}$ ]] || { echo 'Unexpected PostgreSQL integration server version'; exit 2; }
printf 'PostgreSQL integration server version: %s\n' "$pg_check_version"
export DATABASE_URL="postgresql+psycopg://blog_ci@127.0.0.1:$pg_check_port/blog_ci"
export TEST_DATABASE_URL="$DATABASE_URL"
"$ci_python" -m alembic upgrade head
"$ci_python" -m alembic check
"$ci_python" - <<'PY'
import unittest
suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.testsRun == 0 or result.skipped or not result.wasSuccessful():
    raise SystemExit('PostgreSQL integration checks must run successfully with zero skipped tests')
print('PostgreSQL integration checks passed with zero skipped tests.')
PY
