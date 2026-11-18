"""Collect GT4 credentials in a masked dialog and transmit them over SSH stdin."""
import json
import shlex
import subprocess
import sys
from remote import ROOT,ssh_arguments
from configure_geetest_remote import credential_updates


def credentials():
    import tkinter as tk
    from tkinter import simpledialog,messagebox

    class CredentialDialog(simpledialog.Dialog):
        def body(self,master):
            tk.Label(master,text='GeeTest CAPTCHA v4 / Web email login').grid(row=0,columnspan=2,padx=12,pady=8)
            tk.Label(master,text='captcha_id').grid(row=1,column=0,padx=8)
            tk.Label(master,text='captcha_key').grid(row=2,column=0,padx=8)
            self.cid=tk.Entry(master,width=46,show='*');self.cid.grid(row=1,column=1,padx=8,pady=5)
            self.key=tk.Entry(master,width=46,show='*');self.key.grid(row=2,column=1,padx=8,pady=5)
            return self.cid

        def validate(self):
            try:
                credential_updates({'captcha_id':self.cid.get().strip(),'captcha_key':self.key.get().strip()})
                return True
            except ValueError:
                messagebox.showerror('Check credentials','Enter the paired 32-character captcha_id and captcha_key from your GT4 Web scene.',parent=self)
                return False

        def apply(self):
            self.result={'captcha_id':self.cid.get().strip(),'captcha_key':self.key.get().strip()}

    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try: return CredentialDialog(root,title='Blog GeeTest configuration').result
    finally: root.destroy()


def main():
    subprocess.run([sys.executable,str(ROOT/'deploy/setup_ssh.py'),'--check'],check=True)
    values=credentials()
    if values is None: raise SystemExit('Cancelled; server was not changed.')
    credential_updates(values)
    helper=(ROOT/'deploy/configure_mail_remote.py').read_text(encoding='utf-8')
    program=(ROOT/'deploy/configure_geetest_remote.py').read_text(encoding='utf-8')
    bootstrap="_helpers={'__name__':'geetest_config_helpers'}\nexec("+repr(helper)+",_helpers)\nserialize_environment=_helpers['serialize_environment']\nreplace_file=_helpers['replace_file']\n"+program
    print('Installing GT4 configuration; credentials are not logged. Real browser verification is still required.',flush=True)
    result=subprocess.run(ssh_arguments()+['/opt/vueblog/venv/bin/python -c '+shlex.quote(bootstrap)],input=json.dumps(values),text=True,capture_output=True,timeout=120)
    # Only the controlled remote program's fixed status messages may reach the local log.
    report=result.stdout
    log=ROOT/'.local/geetest-setup-status.log';log.parent.mkdir(exist_ok=True)
    log.write_text(report,encoding='utf-8')
    print(report,end='',flush=True)
    if result.returncode: raise SystemExit('GT4 setup did not finish; inspect service status before retrying. Do not share credentials.')


if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError: raise SystemExit('SSH verification failed; credentials were not transmitted.') from None
    except subprocess.TimeoutExpired: raise SystemExit('GT4 setup timed out; check server status before retrying.') from None
    except (OSError,ValueError): raise SystemExit('GT4 setup could not run; credentials were not logged.') from None
