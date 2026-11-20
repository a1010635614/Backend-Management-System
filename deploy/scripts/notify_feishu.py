"""Flow deployment notifications. Credentials come from encrypted variables."""
import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
from urllib.parse import urlsplit


def validate_webhook(webhook):
    import re
    if not isinstance(webhook,str) or any(ord(char)<33 or ord(char)>126 for char in webhook):
        raise ValueError('Invalid webhook')
    parsed=urlsplit(webhook)
    if parsed.scheme!='https' or parsed.netloc!='open.feishu.cn' or parsed.query or parsed.fragment or not re.fullmatch(r'/open-apis/bot/v2/hook/[A-Za-z0-9_-]{10,128}',parsed.path):
        raise ValueError('Invalid webhook')
    return webhook


def payload(result,*,environ=None,timestamp=None):
    if result not in ('success','failure','cancelled','test'): raise ValueError('Unsupported notification result')
    values=os.environ if environ is None else environ
    if result=='test':
        text='纸间博客部署通知\n类型：机器人接入验证\n环境：配置测试\n网站：'+values.get('SITE_URL','https://kongqi.xyz')
    else:
        lines=[f"部署结果：{result}"]
        for key in ('DEPLOY_ENV','BUILD_NUMBER','COMMIT_SHA','BRANCH_NAME','SITE_URL','PIPELINE_URL'):
            lines.append(f"{key}: {values.get(key,'-')}")
        text='纸间博客部署通知\n'+'\n'.join(lines)
    data={'msg_type':'text','content':{'text':text}}
    secret=values.get('FEISHU_SIGNING_SECRET')
    if secret:
        stamp=str(int(time.time()) if timestamp is None else int(timestamp))
        key=f'{stamp}\n{secret}'.encode()
        data.update(timestamp=stamp,sign=base64.b64encode(hmac.new(key,b'',hashlib.sha256).digest()).decode())
    return data


class NotificationError(RuntimeError): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None


def send_notification(webhook,data):
    validate_webhook(webhook)
    request=urllib.request.Request(webhook,data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    try:
        opener=urllib.request.build_opener(NoRedirect)
        with opener.open(request,timeout=15) as response:
            if response.status!=200: raise ValueError('Unexpected response status')
            result=json.load(response)
        code=result.get('code',result.get('StatusCode',-1)) if isinstance(result,dict) else -1
        if type(code) is not int or code!=0: raise ValueError('Notification rejected')
    except Exception:
        raise NotificationError('Feishu delivery was not confirmed. Check the target group and bot settings before retrying.') from None


def main():
    parser=argparse.ArgumentParser(description='Send a Feishu deployment result using encrypted Flow variables.')
    parser.add_argument('result',choices=('success','failure','cancelled','test'))
    parser.add_argument('--preview',action='store_true',help='Print the message text without sending it.')
    args=parser.parse_args()
    data=payload(args.result)
    if args.preview:
        print(data['content']['text'])
        return
    webhook=os.environ.get('FEISHU_WEBHOOK','')
    if not os.environ.get('FEISHU_SIGNING_SECRET'): raise ValueError('Signing secret is required')
    send_notification(webhook,data)
    print('Feishu notification accepted.')


if __name__=='__main__':
    try: main()
    except (ValueError,NotificationError):
        raise SystemExit('Notification delivery was not confirmed; check the target group, webhook and signature before retrying.') from None
