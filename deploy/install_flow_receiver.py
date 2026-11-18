"""Install the reviewed Flow receiver command without changing the running application."""
import base64
import hashlib
import subprocess

from remote import ROOT, ssh_arguments

source = (ROOT / 'deploy/receive_flow_artifact.py').read_bytes()
digest = hashlib.sha256(source).hexdigest()
encoded = base64.b64encode(source).decode('ascii')
script = """set -eu
/usr/bin/python3 - <<'PY'
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if os.geteuid() != 0 or sys.version_info < (3, 12):
    raise SystemExit('Root and Python 3.12+ are required')
source = base64.b64decode(ENCODED_SOURCE)
destination = Path('/usr/local/sbin/vueblog-flow-deploy')
compile(source, str(destination), 'exec')
if destination.is_symlink() or (destination.exists() and destination.read_bytes() != source):
    raise SystemExit('An existing receiver differs; inspect it before replacing')
if not destination.exists():
    fd, name = tempfile.mkstemp(prefix='.vueblog-flow-', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(source)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
if digest != EXPECTED_DIGEST:
    raise SystemExit('Installed receiver checksum differs')
subprocess.run([str(destination), '--help'], check=True, stdout=subprocess.DEVNULL)
print('Flow receiver installed and help checked; SHA-256:', digest)
PY
""".replace('ENCODED_SOURCE', repr(encoded)).replace('EXPECTED_DIGEST', repr(digest))
subprocess.run(ssh_arguments() + ['bash -se'], input=script.encode(), check=True)
