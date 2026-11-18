"""云效通知步骤：python3 deploy/notify.py success|failure。密钥从加密变量读取。"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request

def payload(result):
    lines = [f"部署结果：{result}"]
    for key in ("DEPLOY_ENV", "COMMIT_SHA", "BRANCH_NAME", "SITE_URL", "PIPELINE_URL"):
        lines.append(f"{key}: {os.environ.get(key, '-')}")
    data = {"msg_type": "text", "content": {"text": "纸间博客部署通知\n" + "\n".join(lines)}}
    secret = os.environ.get("FEISHU_SIGNING_SECRET")
    if secret:
        timestamp = str(int(time.time()))
        key = f"{timestamp}\n{secret}".encode()
        data.update(timestamp=timestamp, sign=base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode())
    return data

if __name__ == "__main__":
    webhook = os.environ["FEISHU_WEBHOOK"]
    if not webhook.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/"):
        raise SystemExit("飞书 webhook 格式错误")
    request = urllib.request.Request(webhook, data=json.dumps(payload(sys.argv[1]), ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        if data.get("code", data.get("StatusCode", -1)) != 0:
            raise ValueError("飞书拒绝通知")
    except Exception:
        raise SystemExit("飞书通知失败，请检查凭据和机器人安全配置") from None
