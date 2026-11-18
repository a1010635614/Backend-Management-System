"""Set only the public analytics ID; preserve all credentials and restore on failure."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import httpx


def application_ready(tracking_id):
    for attempt in range(15):
        try:
            health=httpx.get('http://127.0.0.1:8000/api/health',timeout=2)
            config=httpx.get('http://127.0.0.1:8000/api/public/config',timeout=2)
            if health.status_code==200 and health.json()=={'status':'UP'} and config.status_code==200 and config.json()=={'baiduId':tracking_id}:
                return True
        except (httpx.HTTPError,ValueError): pass
        if attempt<14: time.sleep(1)
    return False


def install_tracking_id(tracking_id,envpath=Path('/etc/vueblog.env')):
    if not isinstance(tracking_id,str) or not re.fullmatch(r'[a-f0-9]{32}',tracking_id):
        raise ValueError('Expected the public hm.js tracking ID')
    original=envpath.read_bytes();owner=envpath.stat()
    content=serialize_environment(original.decode(),{'BAIDU_HM_ID':tracking_id}).encode()
    try:
        replace_file(envpath,content,owner)
        subprocess.run(['systemctl','restart','vueblog'],check=True,capture_output=True)
        if not application_ready(tracking_id): raise RuntimeError('Configuration not loaded')
    except Exception:
        try:
            replace_file(envpath,original,owner)
            restored=subprocess.run(['systemctl','restart','vueblog'],capture_output=True)
            if restored.returncode: raise RuntimeError('Restore restart failed')
        except Exception:
            print('Baidu configuration failed; automatic restoration needs inspection.',flush=True)
            raise SystemExit(1) from None
        print('Baidu configuration failed; previous environment restored and service restarted. Check health before retrying.',flush=True)
        raise SystemExit(1) from None
    print('Baidu tracking ID installed; API health and public configuration check: PASS.',flush=True)
    print('Browser tracking requests and the Baidu PV/UV report still require real verification.',flush=True)


def main():
    try: install_tracking_id(json.load(sys.stdin)['tracking_id'])
    except SystemExit: raise
    except Exception:
        print('Baidu configuration could not be prepared; private environment values were not logged.',flush=True)
        raise SystemExit(1) from None


if __name__=='__main__': main()
