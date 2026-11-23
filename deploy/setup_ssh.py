"""由用户在本机交互终端执行；密码由 OpenSSH 提示输入，不由本脚本读取。"""
from pathlib import Path
import base64
import hashlib
import os
import subprocess
import sys
from remote import PRODUCTION_HOST

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/".local"/"ssh"
KEY=STATE/"blog_deploy_ed25519"
KNOWN=STATE/"known_hosts"
KNOWN_OPTION=f'UserKnownHostsFile="{KNOWN.as_posix()}"'
HOST=f"root@{PRODUCTION_HOST}"

def run():
    if "--check" in sys.argv or "--verify-host" in sys.argv:
        interactive="--verify-host" in sys.argv
        options=["ssh","-p","22","-o","ConnectTimeout=15","-o",KNOWN_OPTION,"-i",str(KEY),"-o","IdentitiesOnly=yes","-o","PreferredAuthentications=publickey","-o","BatchMode="+('no' if interactive else 'yes'),"-o","StrictHostKeyChecking="+('ask' if interactive else 'yes')]
        subprocess.run(options+[HOST,"id -un; uname -sr"],check=True)
        print("SSH connection verified.")
        return
    STATE.mkdir(parents=True,exist_ok=True)
    generated=not KEY.exists()
    if generated:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        key=Ed25519PrivateKey.generate()
        with KEY.open("xb") as stream:
            stream.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption()))
    if generated and os.name=="nt":
        identity=subprocess.check_output(["whoami"],text=True).strip()
        subprocess.run(["icacls",str(KEY),"/inheritance:r","/grant:r",identity+":(R)"],check=True,stdout=subprocess.DEVNULL)
    elif generated:
        KEY.chmod(0o600)
    from cryptography.hazmat.primitives import serialization
    key=serialization.load_ssh_private_key(KEY.read_bytes(),password=None)
    public=key.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()+" blog-deploy-kongqi"
    Path(str(KEY)+".pub").write_text(public+"\n",encoding="ascii")
    options=["ssh","-p","22","-o","ConnectTimeout=15","-o",KNOWN_OPTION]
    if "--check" not in sys.argv:
        print("请在 SSH 提示处确认服务器指纹，并输入服务器 root 密码；输入时不会显示字符。",flush=True)
        command='set -eu; umask 077; mkdir -p /root/.ssh; chmod 700 /root/.ssh; touch /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys; key=$(cat); if ! grep -qxF -- "$key" /root/.ssh/authorized_keys; then printf "\\n%s\\n" "$key" >> /root/.ssh/authorized_keys; fi'
        subprocess.run(options+["-o","StrictHostKeyChecking=ask","-o","PreferredAuthentications=password,keyboard-interactive","-o","PubkeyAuthentication=no",HOST,command],input=public+"\n",text=True,check=True)
    subprocess.run(options+["-i",str(KEY),"-o","IdentitiesOnly=yes","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",HOST,"id -un; uname -sr"],check=True)
    print("SSH 密钥登录验证成功。私钥仅保存在本机 .local/ssh，不要提交或分享该目录。")

if __name__=="__main__":
    try: run()
    except (subprocess.CalledProcessError,OSError,ValueError) as error:
        print("SSH 配置未完成："+str(error),file=sys.stderr)
        raise SystemExit(1)
