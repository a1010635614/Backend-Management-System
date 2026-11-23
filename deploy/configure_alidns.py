"""Masked AliDNS setup over pinned SSH; installation never starts DNS validation."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from remote import PRODUCTION_HOST, ROOT, ssh_arguments


def ask_credentials():
    import tkinter as tk
    from tkinter import simpledialog
    window=tk.Tk();window.withdraw();window.attributes('-topmost',True)
    try:
        values={}
        for key,label in (('access_key_id','AccessKey ID'),('access_key_secret','AccessKey Secret')):
            value=simpledialog.askstring('Blog certificate DNS setup',
                f'Target: {PRODUCTION_HOST} / kongqi.xyz\nPurpose: automated DNS-01 certificate renewal\n'
                'Read permission is checked first; credentials are then stored root-only.\n'
                'Installation does not change DNS records or certificates.\n\n'+label+':',
                show='*',parent=window)
            if value is None: return None
            values[key]=value.strip()
        return values
    finally: window.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Ask for credentials, verify read access, then install protected configuration and hooks.')
    args=parser.parse_args()
    scripts=ROOT/'deploy/scripts'
    sys.path.insert(0,str(scripts))
    from install_alidns import plan
    if not args.apply:
        print(json.dumps({'server':PRODUCTION_HOST,**plan()},ensure_ascii=False,indent=2));return
    subprocess.run([sys.executable,str(ROOT/'deploy/setup_ssh.py'),'--check'],check=True)
    credentials=ask_credentials()
    if credentials is None: raise SystemExit('Cancelled; no credentials were transmitted.')
    from alidns_hook import client_from_credentials,HookError
    try: client_from_credentials(credentials)
    except HookError: raise SystemExit('Credential format is invalid; no credentials were transmitted.') from None
    source=(scripts/'alidns_hook.py').read_bytes()
    installer=(scripts/'install_alidns.py').read_text(encoding='utf-8')
    digest=hashlib.sha256(source).hexdigest()
    bootstrap=('import base64,hashlib,json,sys\n'
        'payload=json.loads(sys.stdin.buffer.read(131073))\n'
        'source=base64.b64decode(payload["hook"],validate=True)\n'
        'if hashlib.sha256(source).hexdigest()!='+repr(digest)+': raise SystemExit("AliDNS setup stopped: hook checksum mismatch")\n'
        'namespace={"__name__":"reviewed_alidns_installer"}\n'
        'exec(compile('+repr(installer)+',"<reviewed-install-alidns>","exec"),namespace)\n'
        'try:\n'
        ' result=namespace["install"](source,payload["credentials"])\n'
        ' print(json.dumps(result))\n'
        'except namespace["InstallError"] as error:\n'
        ' raise SystemExit("AliDNS setup stopped: "+str(error)) from None\n'
        'except Exception:\n'
        ' raise SystemExit("AliDNS setup stopped: installation incomplete; inspect the protected paths") from None\n')
    payload=json.dumps({'hook':base64.b64encode(source).decode(),'credentials':credentials}).encode()
    result=subprocess.run(ssh_arguments()+['/usr/bin/python3 -c '+shlex.quote(bootstrap)],input=payload,
                          capture_output=True,timeout=150)
    if result.returncode:
        for line in result.stderr.decode(errors='replace').splitlines():
            if line.startswith('AliDNS setup stopped:'): print(line,file=sys.stderr)
        raise SystemExit('AliDNS setup did not complete. No certificate renewal was started.')
    value=json.loads(result.stdout)
    if value.get('hook_sha256')!=digest or value.get('installed') is not True:
        raise SystemExit('Installation response did not match the reviewed hook.')
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try: main()
    except subprocess.TimeoutExpired:
        raise SystemExit('AliDNS setup timed out; inspect installation before retrying.') from None
    except subprocess.CalledProcessError:
        raise SystemExit('SSH check failed; credentials were not requested.') from None
    except (OSError,ValueError):
        raise SystemExit('AliDNS setup could not finish; credentials were not printed.') from None
