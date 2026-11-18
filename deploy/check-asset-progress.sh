#!/usr/bin/env bash
set -eu
cd /opt/vueblog/current/backend
/opt/vueblog/venv/bin/python - <<'PY'
import os
from dotenv import dotenv_values
os.environ.update({k:v for k,v in dotenv_values('/etc/vueblog.env',interpolate=False).items() if v is not None})
from app.main import SessionLocal,Asset,Post,asset_ids
from sqlalchemy import select,func
with SessionLocal() as db:
    for state,mime,count in db.execute(select(Asset.state,Asset.content_type,func.count()).group_by(Asset.state,Asset.content_type)):
        print('Assets:',state,mime,count)
    references=set()
    for content in db.scalars(select(Post.content)):
        references.update(asset_ids(content))
    if references:
        for mime,count in db.execute(select(Asset.content_type,func.count()).where(Asset.id.in_(references),Asset.state=='ready').group_by(Asset.content_type)):
            print('Article attachments:',mime,count)
    else: print('No article attachment references yet.')
PY
