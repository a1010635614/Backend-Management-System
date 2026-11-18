"""Upload only test sources, then run unprivileged shell checks without changing production."""
import secrets
import subprocess
import tarfile
from remote import ROOT,ssh_arguments

tag='native-check-'+secrets.token_hex(8)
archive=ROOT/'.local'/(tag+'.tar.gz')
archive.parent.mkdir(exist_ok=True)
with tarfile.open(archive,'w:gz') as tar:
    for name in ('release-native.sh','test_native_release.py','test-native-release.py','test_native_artifact.py','stage_native_artifact.py'):
        tar.add(ROOT/'deploy'/name,arcname=name)
target='/opt/vueblog/verification/'+tag
with archive.open('rb') as source:
    subprocess.run(ssh_arguments()+['mkdir -p '+target+' && tar -xzf - -C '+target],stdin=source,check=True)
subprocess.run(ssh_arguments()+['/usr/bin/python3 '+target+'/test-native-release.py'],check=True)
