"""Install a public Baidu hm.js tracking ID through the existing SSH connection."""
import argparse
import json
import re
import shlex
import subprocess
import sys
from remote import ROOT,ssh_arguments


def main():
    parser=argparse.ArgumentParser(description='Configure the public 32-character Baidu hm.js tracking ID.')
    parser.add_argument('tracking_id')
    value=parser.parse_args().tracking_id
    if not re.fullmatch(r'[a-f0-9]{32}',value): raise SystemExit('Enter only the lowercase 32-character ID after hm.js?, not the numeric siteId or complete script.')
    subprocess.run([sys.executable,str(ROOT/'deploy/setup_ssh.py'),'--check'],check=True)
    helper=(ROOT/'deploy/configure_mail_remote.py').read_text(encoding='utf-8')
    program=(ROOT/'deploy/configure_baidu_remote.py').read_text(encoding='utf-8')
    bootstrap="_helpers={'__name__':'baidu_config_helpers'}\nexec("+repr(helper)+",_helpers)\nserialize_environment=_helpers['serialize_environment']\nreplace_file=_helpers['replace_file']\n"+program
    result=subprocess.run(ssh_arguments()+['/opt/vueblog/venv/bin/python -c '+shlex.quote(bootstrap)],input=json.dumps({'tracking_id':value}),text=True,capture_output=True,timeout=120)
    print(result.stdout,end='',flush=True)
    if result.returncode: raise SystemExit('Baidu configuration did not finish. Check server service status before retrying.')


if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError: raise SystemExit('SSH verification failed; server was not configured.') from None
    except subprocess.TimeoutExpired: raise SystemExit('Configuration timed out; check server status before retrying.') from None
    except OSError: raise SystemExit('Configuration tool could not run.') from None
