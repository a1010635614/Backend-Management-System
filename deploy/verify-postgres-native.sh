#!/usr/bin/env bash
set -eu
cd /opt/vueblog/current/backend
/opt/vueblog/venv/bin/python - <<'PY'
import os,secrets,subprocess
def psql(sql):
    return subprocess.run(['runuser','-u','postgres','--','psql','-v','ON_ERROR_STOP=1','-Atc',sql],check=True,capture_output=True,text=True).stdout.strip()
if psql("select 1 from pg_roles where rolname='blog_ci'") or psql("select 1 from pg_database where datname='blog_ci'"):
    raise SystemExit('Existing blog_ci resources found; refusing to overwrite.')
password=secrets.token_hex(24)
psql("create role blog_ci login password '"+password+"'")
try:
    psql('create database blog_ci owner blog_ci')
    url='postgresql+psycopg://blog_ci:'+password+'@127.0.0.1:5432/blog_ci'
    env={**os.environ,'DATABASE_URL':url,'TEST_DATABASE_URL':url}
    for command in (['-m','alembic','upgrade','head'],['-m','alembic','check'],['-m','unittest','discover','-s','tests','-v']):
        subprocess.run(['/opt/vueblog/venv/bin/python',*command],env=env,check=True)
finally:
    psql('drop database if exists blog_ci')
    psql('drop role blog_ci')
PY
