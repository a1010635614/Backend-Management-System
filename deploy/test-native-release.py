"""Run shell control-flow checks as an unprivileged user with isolated fake commands."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    if os.name!='posix' or sys.version_info<(3,12):
        raise SystemExit('Use Linux with Python 3.12+ for native release control-flow checks.')
    source=Path(__file__).resolve().parent
    if os.geteuid()!=0:
        subprocess.run([sys.executable,'-m','unittest','discover','-s',str(source),'-p','test_native_release.py','-v'],check=True)
    else:
        with tempfile.TemporaryDirectory(prefix='vueblog-release-tests-',dir='/tmp') as work:
            sandbox=Path(work);sandbox.chmod(0o755)
            for name in ('test_native_release.py','release-native.sh'):
                shutil.copyfile(source/name,sandbox/name)
                (sandbox/name).chmod(0o644)
            subprocess.run(['runuser','-u','nobody','--',sys.executable,'-m','unittest','discover','-s',str(sandbox),'-p','test_native_release.py','-v'],cwd=sandbox,check=True)
    print('Native release control-flow checks passed with simulated runtime, service and HTTP commands. Real Flow deployment/rollback remains unverified.')


if __name__=='__main__': main()
