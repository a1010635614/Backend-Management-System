"""Test a bot with masked credentials and explicit message confirmation; persist no secrets."""
from notify import payload,validate_webhook,send_notification,NotificationError


def validate_credentials(values):
    group=values.get('group','').strip()
    webhook=values.get('webhook','').strip()
    secret=values.get('secret','').strip()
    if not group or len(group)>80 or any(ord(char)<32 for char in group): raise ValueError('Group name is required')
    validate_webhook(webhook)
    if not secret or len(secret)>256 or any(ord(char)<33 or ord(char)>126 for char in secret):
        raise ValueError('Signing secret is required')
    return {'group':group,'webhook':webhook,'secret':secret}


def credentials():
    import tkinter as tk
    from tkinter import simpledialog,messagebox

    class CredentialDialog(simpledialog.Dialog):
        def body(self,master):
            tk.Label(master,text='飞书机器人连接验证\n凭据仅在内存中使用，随后还需填入云效加密变量。').grid(row=0,columnspan=2,padx=12,pady=8)
            self.entries={}
            for row,(name,label,masked) in enumerate((('group','群名称（供你核对）',False),('webhook','Webhook 地址',True),('secret','签名密钥',True)),start=1):
                tk.Label(master,text=label).grid(row=row,column=0,padx=8)
                entry=tk.Entry(master,width=58,show='*' if masked else '')
                entry.grid(row=row,column=1,padx=8,pady=5)
                self.entries[name]=entry
            return self.entries['group']

        def validate(self):
            try:
                validate_credentials({key:entry.get() for key,entry in self.entries.items()})
                return True
            except ValueError:
                messagebox.showerror('检查输入','请填写群名称、完整的飞书自定义机器人 Webhook 和签名密钥。不要填写 App ID 或 App Secret。',parent=self)
                return False

        def apply(self): self.result=validate_credentials({key:entry.get() for key,entry in self.entries.items()})

    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try: return CredentialDialog(root,title='Blog Feishu configuration').result
    finally: root.destroy()


def confirm_send(group,text):
    import tkinter as tk
    from tkinter import messagebox
    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try:
        return messagebox.askyesno('确认发送飞书测试通知','你填写的目标群：'+group+'\n实际目标由 Webhook 绑定的群决定。请核对这两者一致。\n\n将发送以下完整正文：\n\n'+text+'\n\n是否发送这一条测试通知？',parent=root)
    finally: root.destroy()


def main():
    values=credentials()
    if values is None:
        print('Cancelled; no notification sent.')
        return
    values=validate_credentials(values)
    preview=payload('test',environ={'SITE_URL':'https://kongqi.xyz'})['content']['text']
    if not confirm_send(values['group'],preview):
        print('Cancelled; no notification sent.')
        return
    # Sign only after confirmation so the timestamp remains fresh.
    data=payload('test',environ={'SITE_URL':'https://kongqi.xyz','FEISHU_SIGNING_SECRET':values['secret']})
    send_notification(values['webhook'],data)
    print('Feishu accepted the one confirmed test notification. Check that it arrived in the intended group.')
    print('No credentials were saved. Add the same webhook and secret to encrypted Flow variables when configuring the pipeline.')


if __name__=='__main__':
    try: main()
    except (ValueError,NotificationError,OSError):
        raise SystemExit('Feishu verification did not finish; credentials were not logged. Check the target group and bot settings before retrying.') from None
