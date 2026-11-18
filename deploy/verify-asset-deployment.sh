#!/usr/bin/env bash
set -eu
cd /opt/vueblog/current/backend
/opt/vueblog/venv/bin/python - <<'PY'
import os
from dotenv import dotenv_values
os.environ.update({k:v for k,v in dotenv_values('/etc/vueblog.env',interpolate=False).items() if v is not None})
from app.main import engine,SessionLocal,User
from sqlalchemy import text,select
with engine.connect() as connection:
    print('Database migration:',connection.execute(text('select version_num from alembic_version')).scalar_one())
    print('Asset table:',connection.execute(text("select to_regclass('public.assets') is not null")).scalar_one())
with SessionLocal() as db:
    print('Administrator user retained:',db.scalar(select(User.id).where(User.email=='kongqi_company@163.com')) is not None)
PY
curl -fsS --resolve kongqi.xyz:443:127.0.0.1 https://kongqi.xyz/api/health
