#!/usr/bin/env bash
set -eu
systemctl is-active vueblog
cd /opt/vueblog/current/backend
/opt/vueblog/venv/bin/python - <<'PY'
import os,smtplib,ssl,sys,urllib.request
from dotenv import dotenv_values
values={k:v for k,v in dotenv_values('/etc/vueblog.env',interpolate=False).items() if v is not None}
required=['MAIL_HOST','MAIL_PORT','MAIL_USERNAME','MAIL_PASSWORD','MAIL_FROM','ADMIN_EMAILS']
missing=[key for key in required if not values.get(key)]
if missing: raise SystemExit('Missing configuration fields: '+', '.join(missing))
os.environ.update(values)
from app.main import settings
from app.mailer import send_message
assert settings.mail_host=='smtpdm.aliyun.com' and settings.mail_port==465,'Unexpected SMTP endpoint'
assert settings.mail_username==settings.mail_from=='noreply@mail.kongqi.xyz','Unexpected sender'
assert 'kongqi_company@163.com' in values['ADMIN_EMAILS'].split(','),'Administrator missing'
try:
    with smtplib.SMTP_SSL(settings.mail_host,settings.mail_port,timeout=15,context=ssl.create_default_context()) as smtp:
        smtp.login(settings.mail_username,settings.mail_password)
        print('SMTP TLS/authentication: PASS (no email sent)')
except smtplib.SMTPAuthenticationError as error:
    raise SystemExit('SMTP authentication failed, code '+str(error.smtp_code)) from None
except Exception as error:
    raise SystemExit('SMTP transport failed: '+type(error).__name__) from None
print('SSL-capable mailer installed; administrator allowlist: PASS')
with urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=8) as response:
    print('API health:',response.read().decode())
PY
