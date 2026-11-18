"""Inspect public SSH host-file configuration without reading private keys."""
from pathlib import Path
import subprocess
from remote import ssh_arguments
args=ssh_arguments()
result=subprocess.run([args[0],'-G',*args[1:]],capture_output=True,text=True)
for line in result.stdout.splitlines():
    if line.startswith(('userknownhostsfile ','hostname ','identityfile ')): print(line)
for path in (Path('G:/Full'),Path('G:/Full Stack/agent full stack project/.local/ssh/known_hosts')):
    try: print(str(path), 'file exists' if path.is_file() else 'not a file')
    except OSError: print(str(path),'cannot inspect')
