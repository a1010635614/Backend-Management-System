#!/usr/bin/env bash
set -eu
if [ -f /etc/vueblog.env ]; then /usr/local/sbin/vueblog-backup; fi
release="/opt/vueblog/releases/$(date -u +%Y%m%d%H%M%S)"
mkdir -p "$release"
tar -xzf /opt/vueblog/release.tar.gz -C "$release"
chown -R blog:blog "$release"
chmod 755 /opt/vueblog /opt/vueblog/releases "$release" "$release/frontend"
python3 -m venv /opt/vueblog/venv
/opt/vueblog/venv/bin/pip install --disable-pip-version-check --no-cache-dir -q -r "$release/backend/requirements.txt"
python3 - <<'PY'
from pathlib import Path
import grp,os,secrets,subprocess
env=Path('/etc/vueblog.env')
def psql(sql):
    return subprocess.run(['runuser','-u','postgres','--','psql','-v','ON_ERROR_STOP=1','-Atc',sql],check=True,capture_output=True,text=True).stdout.strip()
if not env.exists():
    password=secrets.token_hex(32)
    if psql("select 1 from pg_roles where rolname='blog'"):
        raise SystemExit('Existing blog role requires manual configuration; no password changed.')
    psql("create role blog login password '"+password+"'")
    psql('create database blog owner blog')
    env.write_text('DATABASE_URL=postgresql+psycopg://blog:'+password+'@127.0.0.1:5432/blog\nJWT_SECRET='+secrets.token_hex(48)+'\nCORS_ORIGINS=https://kongqi.xyz\nADMIN_EMAILS=\nMAIL_HOST=\nGEETEST_ID=\nCOS_SECRET_ID=\nBAIDU_HM_ID=\n')
    os.chown(env,0,grp.getgrnam('blog').gr_gid)
    env.chmod(0o640)
print('Database and private environment configuration ready.')
PY
cd "$release/backend"
/opt/vueblog/venv/bin/python - <<'PY'
import os,subprocess
from dotenv import dotenv_values
env={**os.environ,**{k:v for k,v in dotenv_values('/etc/vueblog.env',interpolate=False).items() if v is not None}}
for args in (['upgrade','head'],['check']):
    subprocess.run(['/opt/vueblog/venv/bin/python','-m','alembic',*args],env=env,check=True)
PY
ln -sfn "$release" /opt/vueblog/current
cat > /etc/systemd/system/vueblog.service <<'UNIT'
[Unit]
Description=VueBlog FastAPI
After=network.target postgresql.service
Requires=postgresql.service
[Service]
User=blog
Group=blog
WorkingDirectory=/opt/vueblog/current/backend
EnvironmentFile=/etc/vueblog.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/vueblog/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
UMask=0027
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now vueblog
systemctl restart vueblog
if [ ! -f /etc/nginx/sites-available/vueblog ]; then
cat > /etc/nginx/sites-available/vueblog <<'NGINX'
limit_req_zone $binary_remote_addr zone=vueblog_auth:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=vueblog_events:10m rate=30r/m;
server {
    listen 80;
    server_name kongqi.xyz;
    root /opt/vueblog/current/frontend/dist;
    index index.html;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location /assets/ { try_files $uri =404; add_header Cache-Control "public, max-age=31536000, immutable"; }
    location / { try_files $uri $uri/ /index.html; add_header Cache-Control "no-store" always; }
    location /api/auth/ {
        limit_req zone=vueblog_auth burst=5 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        add_header Cache-Control "no-store" always;
    }
    location = /api/analytics/events {
        limit_req zone=vueblog_events burst=10 nodelay;
        limit_req_status 429;
        client_max_body_size 8k;
        proxy_pass http://127.0.0.1:8000;
        add_header Cache-Control "no-store" always;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        add_header Cache-Control "no-store" always;
    }
    location = /docs { proxy_pass http://127.0.0.1:8000; }
    location = /openapi.json { proxy_pass http://127.0.0.1:8000; }
}
NGINX
fi
ln -sfn /etc/nginx/sites-available/vueblog /etc/nginx/sites-enabled/vueblog
nginx -t
systemctl reload nginx
healthy=false
for retry in $(seq 1 15); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/api/health 2>/dev/null; then healthy=true; break; fi
    sleep 1
done
"$healthy" || { echo 'API failed health check'; exit 1; }
if [ -f /etc/letsencrypt/live/kongqi.xyz/fullchain.pem ]; then
    curl -fsS --max-time 10 --resolve kongqi.xyz:443:127.0.0.1 https://kongqi.xyz/api/health
else
    curl -fsS --max-time 10 -H 'Host: kongqi.xyz' http://127.0.0.1/api/health
fi
systemctl is-active vueblog postgresql nginx
