"""Invoked through SSH stdin by configure_mail.py. Never prints credentials."""
import io
import json
import os
from pathlib import Path
import smtplib
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from dotenv import dotenv_values

def serialize_environment(original, updates):
    values=dict(dotenv_values(stream=io.StringIO(original),interpolate=False))
    values.update(updates)
    for key,value in values.items():
        if not key.replace('_','').isalnum() or not key[0].isalpha():
            raise ValueError('Unsupported environment key')
        if value is not None and any(ord(c)<32 or ord(c)>126 for c in value):
            raise ValueError('Environment values must be single-line ASCII')
    return ''.join(key+'='+json.dumps(value or '')+'\n' for key,value in values.items())

def replace_file(path,data,owner):
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),owner.st_mode & 0o777)
            os.fchown(stream.fileno(),owner.st_uid,owner.st_gid)
            stream.write(data)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def main():
    payload=json.load(sys.stdin)
    password=payload['password']
    updates={'MAIL_HOST':'smtpdm.aliyun.com','MAIL_PORT':'465',
             'MAIL_USERNAME':'noreply@mail.kongqi.xyz','MAIL_FROM':'noreply@mail.kongqi.xyz',
             'MAIL_PASSWORD':password,'ADMIN_EMAILS':'kongqi_company@163.com'}
    envpath=Path('/etc/vueblog.env')
    original=envpath.read_bytes()
    new_env=serialize_environment(original.decode(),updates).encode()
    files={Path('/opt/vueblog/current/backend/app')/name:payload['files'][name].encode() for name in ('main.py','mailer.py')}
    for path,content in files.items(): compile(content,str(path),'exec')
    # Verify TLS and SMTP authentication without sending email.
    try:
        with smtplib.SMTP_SSL(updates['MAIL_HOST'],465,timeout=15,context=ssl.create_default_context()) as smtp:
            smtp.login(updates['MAIL_USERNAME'],password)
    except smtplib.SMTPAuthenticationError as error:
        raise SystemExit('SMTP authentication rejected, code '+str(error.smtp_code)+'. Check the DirectMail sender, region and SMTP password; configuration was not changed.') from None
    except Exception as error:
        raise SystemExit('SMTP TLS/connection check failed ('+type(error).__name__+'); configuration was not changed.') from None
    print('SMTP TLS and authentication verified. No message sent.',flush=True)
    snapshots={p:(p.read_bytes(),p.stat()) if p.exists() else None for p in files}
    snapshots[envpath]=(original,envpath.stat())
    try:
        for path,content in files.items():
            owner=snapshots[path][1] if snapshots[path] else snapshots[Path('/opt/vueblog/current/backend/app/main.py')][1]
            replace_file(path,content,owner)
        replace_file(envpath,new_env,snapshots[envpath][1])
        subprocess.run(['systemctl','restart','vueblog'],check=True,capture_output=True)
        for attempt in range(15):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2) as response:
                    if response.status==200: break
            except Exception:
                if attempt==14: raise RuntimeError('Health check failed')
                time.sleep(1)
        else: raise RuntimeError('Health check failed')
    except Exception:
        for path,snapshot in snapshots.items():
            if snapshot: replace_file(path,*snapshot)
            elif path.exists(): path.unlink()
        subprocess.run(['systemctl','restart','vueblog'],capture_output=True)
        raise SystemExit('Deployment failed; original code and configuration restored. Inspect server service status.') from None
    print('Mail configuration and SSL-capable backend installed; health check passed.')

if __name__=='__main__':
    main()
