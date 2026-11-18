#!/usr/bin/env bash
set -eu
cd /opt/vueblog/current/backend
/opt/vueblog/venv/bin/python - <<'PY'
import os
from datetime import datetime,timedelta,timezone
from dotenv import dotenv_values
os.environ.update({key:value for key,value in dotenv_values('/etc/vueblog.env',interpolate=False).items() if value is not None})
from sqlalchemy import select,func
from app.main import SessionLocal,Event
now=datetime.now(timezone.utc)
with SessionLocal() as db:
    for label,start in (('Today UTC',now.replace(hour=0,minute=0,second=0,microsecond=0)),('Last 15 minutes',now-timedelta(minutes=15))):
        pv,uv=db.execute(select(func.count(Event.id),func.count(func.distinct(Event.visitor_id))).where(Event.event_name=='pageview',Event.created_at>=start)).one()
        print(label+': first-party PV='+str(pv)+', UV='+str(uv),flush=True)
    latest=db.scalar(select(func.max(Event.created_at)).where(Event.event_name=='pageview'))
    print('Latest first-party pageview UTC: '+(latest.astimezone(timezone.utc).isoformat() if latest else 'none'),flush=True)
print('These are application database counts, not the Baidu report.')
PY
