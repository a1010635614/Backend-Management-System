"""Collect COS credentials in a masked local dialog, transmit only over SSH."""
import json
import shlex
import subprocess
import sys
from remote import ROOT,ssh_arguments

def credentials():
    import tkinter as tk
    from tkinter import simpledialog
    class CredentialDialog(simpledialog.Dialog):
        def body(self,master):
            tk.Label(master,text='Bucket: kongqi-agent-1317119844\nRegion: ap-shanghai').grid(row=0,columnspan=2,padx=12,pady=8)
            tk.Label(master,text='SecretId').grid(row=1,column=0,padx=8)
            tk.Label(master,text='SecretKey').grid(row=2,column=0,padx=8)
            self.sid=tk.Entry(master,width=46,show='*');self.sid.grid(row=1,column=1,padx=8,pady=5)
            self.key=tk.Entry(master,width=46,show='*');self.key.grid(row=2,column=1,padx=8,pady=5)
            return self.sid
        def validate(self): return bool(self.sid.get().strip() and self.key.get().strip())
        def apply(self): self.result=(self.sid.get().strip(),self.key.get().strip())
    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try: return CredentialDialog(root,title='Blog COS configuration').result
    finally: root.destroy()

def main():
    subprocess.run([sys.executable,str(ROOT/'deploy/setup_ssh.py'),'--verify-host'],check=True)
    values=credentials()
    if not values: raise SystemExit('Cancelled; server was not changed.')
    if any(ord(c)<33 or ord(c)>126 for v in values for c in v): raise SystemExit('Credentials must contain printable ASCII without spaces.')
    # Reuse the tested environment serialization/atomic write helpers without running mail setup.
    helper=(ROOT/'deploy/configure_mail_remote.py').read_text(encoding='utf-8')
    program=(ROOT/'deploy/configure_cos_remote.py').read_text(encoding='utf-8')
    bootstrap="_helpers={'__name__':'cos_config_helpers'}\nexec("+repr(helper)+",_helpers)\nserialize_environment=_helpers['serialize_environment']\nreplace_file=_helpers['replace_file']\n"+program
    print('Verifying COS read/write, private access, and CORS; credentials are not logged.',flush=True)
    result=subprocess.run(ssh_arguments()+['/opt/vueblog/venv/bin/python -c '+shlex.quote(bootstrap)],input=json.dumps({'secret_id':values[0],'secret_key':values[1]}),text=True,capture_output=True,timeout=150)
    report=result.stdout+result.stderr
    log=ROOT/'.local/cos-setup-status.log';log.parent.mkdir(exist_ok=True);log.write_text(report,encoding='utf-8')
    print(report,end='',flush=True)
    if result.returncode: raise SystemExit('COS setup did not finish. Do not share credentials in error reports.')

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError: raise SystemExit('SSH verification failed; credentials were not transmitted.') from None
    except subprocess.TimeoutExpired: raise SystemExit('COS setup timed out; server status must be checked before retrying.') from None
