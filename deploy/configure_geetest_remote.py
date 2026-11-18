"""Invoked by configure_geetest.py with atomic environment helpers bound."""
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx


def credential_updates(payload):
    if not isinstance(payload,dict): raise ValueError('Expected paired GT4 credentials')
    values={name:payload.get(name) for name in ('captcha_id','captcha_key')}
    if any(not isinstance(value,str) or len(value)!=32 or any(ord(char)<33 or ord(char)>126 for char in value) for value in values.values()):
        raise ValueError('Expected paired 32-character GT4 credentials')
    return {'GEETEST_ID':values['captcha_id'],'GEETEST_KEY':values['captcha_key']}


def application_ready(captcha_id):
    for attempt in range(15):
        try:
            health=httpx.get('http://127.0.0.1:8000/api/health',timeout=2)
            config=httpx.get('http://127.0.0.1:8000/api/auth/config',timeout=2)
            if health.status_code==200 and health.json()=={'status':'UP'} and config.status_code==200 and config.json()=={'captchaId':captcha_id}:
                return True
        except (httpx.HTTPError,ValueError):
            pass
        if attempt<14: time.sleep(1)
    return False


def install_credentials(payload,envpath=Path('/etc/vueblog.env')):
    updates=credential_updates(payload)
    original=envpath.read_bytes();owner=envpath.stat()
    content=serialize_environment(original.decode(),updates).encode()
    try:
        replace_file(envpath,content,owner)
        subprocess.run(['systemctl','restart','vueblog'],check=True,capture_output=True)
        if not application_ready(updates['GEETEST_ID']): raise RuntimeError('Configuration not loaded')
    except Exception:
        try:
            replace_file(envpath,original,owner)
            restored=subprocess.run(['systemctl','restart','vueblog'],capture_output=True)
            if restored.returncode: raise RuntimeError('Restore restart failed')
        except Exception:
            print('GT4 configuration failed; automatic restoration needs inspection.',flush=True)
            raise SystemExit(1) from None
        print('GT4 configuration failed; previous environment restored and service restarted. Check health before retrying.',flush=True)
        raise SystemExit(1) from None
    print('GT4 configuration installed; API health and public captcha ID check: PASS.',flush=True)
    print('The captcha key has NOT been validated with GeeTest. Complete real browser verification, email delivery and login before accepting this integration.',flush=True)


def main():
    try:
        install_credentials(json.load(sys.stdin))
    except SystemExit:
        raise
    except Exception:
        print('GT4 configuration could not be prepared; credentials were not logged.',flush=True)
        raise SystemExit(1) from None


if __name__=='__main__': main()
