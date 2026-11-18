"""Forward the remote API for a private, local Vue preview; no public listener."""
import subprocess
from remote import ssh_arguments

args=ssh_arguments()
args[-1:-1]=['-N','-o','ExitOnForwardFailure=yes','-L','127.0.0.1:8000:127.0.0.1:8000']
print('Remote API tunnel: http://127.0.0.1:8000 (Ctrl+C to stop)',flush=True)
subprocess.run(args,check=True)
