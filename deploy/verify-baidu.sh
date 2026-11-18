#!/usr/bin/env bash
set -eu
/opt/vueblog/venv/bin/python - <<'PY'
import re
import httpx
with httpx.Client(timeout=15) as client:
    response=client.get('http://127.0.0.1:8000/api/public/config')
    response.raise_for_status()
    tracking_id=response.json().get('baiduId','')
    if not re.fullmatch(r'[a-f0-9]{32}',tracking_id):
        raise SystemExit('Baidu tracking ID is not configured.')
    print('Public analytics configuration: present',flush=True)
    script=client.get('https://hm.baidu.com/hm.js?'+tracking_id,headers={'Referer':'https://kongqi.xyz/'})
    print('Baidu script: HTTP '+str(script.status_code)+', '+str(len(script.content))+' bytes',flush=True)
    print('Content-Type: '+script.headers.get('content-type','unknown'),flush=True)
    if script.status_code!=200 or len(script.content)<100:
        raise SystemExit('Script fetch was not usable; browser collection and dashboard records remain unverified.')
    print('Script is available; real browser collection and dashboard PV/UV still need verification.')
PY
