"""Run a reviewed deployment shell script over the configured SSH connection."""
from pathlib import Path
from ipaddress import ip_address
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PRODUCTION_HOST = "121.40.113.185"
LEGACY_HOST = "101.37.147.237"


def ssh_arguments(*, host: str = PRODUCTION_HOST):
    """Use the verified replacement by default; old-host access must be explicit."""
    address = str(ip_address(host))
    arguments = ["ssh","-p","22","-o","ConnectTimeout=15","-o","ServerAliveInterval=15","-o","ServerAliveCountMax=3","-o",f'UserKnownHostsFile="{(ROOT/".local/ssh/known_hosts").as_posix()}"',"-i",str(ROOT/".local/ssh/blog_deploy_ed25519"),"-o","IdentitiesOnly=yes","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes"]
    if address == PRODUCTION_HOST:
        # Only this host's ED25519 key was verified through the cloud console.
        arguments += ["-o", "HostKeyAlgorithms=ssh-ed25519"]
    return arguments + [f"root@{address}"]

if __name__=="__main__":
    script=Path(sys.argv[1]).resolve()
    script.relative_to(ROOT/"deploy")
    subprocess.run(ssh_arguments()+["bash -se"],input=script.read_bytes(),check=True)
