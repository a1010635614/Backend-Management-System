"""Run interactively on the user's PC. Secret travels only in SSH stdin."""
import getpass
import json
from pathlib import Path
import shlex
import subprocess
import sys
from remote import ROOT,ssh_arguments

LOG=ROOT/'.local/mail-setup-status.log'

def status(message):
    print(message,flush=True)
    with LOG.open('a',encoding='utf-8') as output: output.write(message+'\n')

def read_password():
    if sys.platform=='win32' and '--console-password' not in sys.argv:
        import tkinter as tk
        from tkinter import simpledialog
        window=tk.Tk()
        window.withdraw()
        window.attributes('-topmost',True)
        try:
            return simpledialog.askstring('Blog SMTP configuration','SMTP password (hidden; not the server root password):',show='*',parent=window)
        finally: window.destroy()
    return getpass.getpass('SMTP password: ')

def main():
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text('Mail setup started. No passwords are logged.\n',encoding='utf-8')
    if '--diagnose' in sys.argv:
        probe="import json,sys,ssl,smtplib; assert json.load(sys.stdin)['probe']; s=smtplib.SMTP_SSL('smtpdm.aliyun.com',465,timeout=15,context=ssl.create_default_context()); print('SSH stdin transport: PASS'); print('Server SMTP TLS: '+s.sock.version()); print('SMTP EHLO: '+str(s.ehlo()[0])); s.quit()"
        result=subprocess.run(ssh_arguments()+['/opt/vueblog/venv/bin/python -c '+shlex.quote(probe)],input=json.dumps({'probe':True}),text=True,capture_output=True,timeout=90)
        status(result.stdout+result.stderr)
        if result.returncode: raise SystemExit('Diagnostic failed. No password was requested or transmitted.')
        return
    # Human checks host identity before any secret is requested or transmitted.
    status('Stage 1/3: checking SSH host and key.')
    subprocess.run([sys.executable,str(ROOT/'deploy/setup_ssh.py'),'--verify-host'],check=True)
    if (sys.platform!='win32' or '--console-password' in sys.argv) and not sys.stdin.isatty():
        raise SystemExit('Please run this in your own interactive terminal.')
    print('Sender: noreply@mail.kongqi.xyz; administrator: kongqi_company@163.com')
    print('Enter the current/reset SMTP password below; it will not be displayed or saved locally.')
    status('Stage 2/3: waiting for password input (a masked dialog opens on Windows).')
    password=read_password()
    if not password or any(ord(c)<32 or ord(c)>126 for c in password):
        raise SystemExit('Password must be nonempty single-line ASCII.')
    payload={'password':password,'files':{'mailer.py':(ROOT/'backend/app/mailer.py').read_text(encoding='utf-8')}}
    program=(ROOT/'deploy/configure_mail_remote.py').read_text(encoding='utf-8')
    command='/opt/vueblog/venv/bin/python -c '+shlex.quote(program)
    status('Stage 3/3: checking SMTP authentication and applying configuration...')
    result=subprocess.run(ssh_arguments()+[command],input=json.dumps(payload),text=True,capture_output=True,timeout=120)
    # Only the remote program's status output is logged, never its input payload.
    report=result.stdout+result.stderr
    status(report)
    if result.returncode: raise SystemExit('Configuration did not finish; check the preceding status. Do not share passwords in error reports.')
    status('Done. You can request a login code for kongqi_company@163.com from the login page.')

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError:
        status('SSH verification failed; no SMTP password was transmitted.')
        raise SystemExit(1) from None
    except (KeyboardInterrupt,EOFError):
        status('Input was cancelled or ended; configuration was not completed.')
        raise SystemExit(1) from None
    except subprocess.TimeoutExpired:
        status('Operation timed out. Server state must be checked before retrying.')
        raise SystemExit(1) from None
    except SystemExit as error:
        if error.code and isinstance(error.code,str): status(error.code)
        raise
