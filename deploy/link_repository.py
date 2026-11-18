"""在当前项目关联用户指定的 GitHub 仓库，不创建远程提交或推送代码。"""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
URL="https://github.com/a1010635614/Backend-Management-System.git"
def git(*args):
    return subprocess.run(["git","-c",f"safe.directory={ROOT.as_posix()}",*args],cwd=ROOT,check=True,capture_output=True,text=True)

if __name__=="__main__":
    names=git("remote").stdout.splitlines()
    if "origin" in names:
        current=git("remote","get-url","origin").stdout.strip()
        if current!=URL: raise SystemExit("origin 已指向其他仓库，请人工核对")
    else: git("remote","add","origin",URL)
    print("已关联仓库："+URL)
