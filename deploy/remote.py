"""Run a reviewed deployment shell script over the configured SSH connection."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def ssh_arguments():
    return ["ssh","-p","22","-o","ConnectTimeout=15","-o","ServerAliveInterval=15","-o","ServerAliveCountMax=3","-o",f'UserKnownHostsFile="{(ROOT/".local/ssh/known_hosts").as_posix()}"',"-i",str(ROOT/".local/ssh/blog_deploy_ed25519"),"-o","IdentitiesOnly=yes","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@101.37.147.237"]

if __name__=="__main__":
    script=Path(sys.argv[1]).resolve()
    script.relative_to(ROOT/"deploy")
    subprocess.run(ssh_arguments()+["bash -se"],input=script.read_bytes(),check=True)
