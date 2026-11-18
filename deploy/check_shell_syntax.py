"""Parse deployment scripts with server Bash; never execute their contents."""
import subprocess
from remote import ROOT,ssh_arguments
files=sorted((ROOT/'deploy').glob('*.sh'))
source='\n\n'.join(path.read_text(encoding='utf-8') for path in files)
subprocess.run(ssh_arguments()+['bash -n'],input=source.encode('utf-8'),check=True)
print(f'Bash syntax passed for {len(files)} deployment scripts; none executed.')
