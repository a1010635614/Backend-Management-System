#!/usr/bin/env bash
set -eu
systemctl is-active vueblog nginx postgresql
/opt/vueblog/venv/bin/python - <<'PY'
from dotenv import dotenv_values
c=dotenv_values('/etc/vueblog.env')
groups={
    'Admin allowlist':['ADMIN_EMAILS'],
    'SMTP':['MAIL_HOST','MAIL_USERNAME','MAIL_PASSWORD','MAIL_FROM'],
    'GeeTest':['GEETEST_ID','GEETEST_KEY'],
    'COS':['COS_SECRET_ID','COS_SECRET_KEY','COS_REGION','COS_BUCKET','COS_PUBLIC_BASE_URL'],
    'Baidu analytics':['BAIDU_HM_ID'],
}
for name,keys in groups.items():
    missing=[k for k in keys if not c.get(k)]
    print(name+(': configured (needs live verification)' if not missing else ': missing '+', '.join(missing)))
PY
printf '\nPublic HTTP\n'
curl -sI --max-time 10 http://kongqi.xyz | head -6
printf '\nHTTPS health\n'
curl -fsS --max-time 10 https://kongqi.xyz/api/health
