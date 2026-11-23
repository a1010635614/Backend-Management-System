"""Install only the reviewed, verify-only Flow staging entry on the new host."""
import base64
import hashlib
import json
import shlex
import subprocess
from remote import ROOT,ssh_arguments


def main():
    names=('artifact.py','receive.py','flow_host.py','verify_flow.py')
    files={name:(ROOT/'deploy/scripts'/name).read_bytes() for name in names}
    expected={name:hashlib.sha256(value).hexdigest() for name,value in files.items()}
    source=r'''import base64,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
base=Path('/usr/local/lib/blog-flow-validation')
if os.geteuid()!=0 or base.resolve()!=base or base.is_symlink(): raise SystemExit('Unexpected verifier install directory')
base.mkdir(parents=True,exist_ok=True,mode=0o755)
if base.stat().st_uid!=0 or base.stat().st_mode&0o022: raise SystemExit('Verifier directory is not protected')
values=json.loads(sys.stdin.buffer.read(262145))
expected=EXPECTED
if set(values)!=set(expected): raise SystemExit('Unexpected verifier files')
decoded={name:base64.b64decode(value,validate=True) for name,value in values.items()}
for name,value in decoded.items():
    if hashlib.sha256(value).hexdigest()!=expected[name]: raise SystemExit('Verifier source checksum mismatch')
    compile(value,str(base/name),'exec')
    target=base/name
    if target.is_symlink() or target.resolve()!=target: raise SystemExit('Verifier file must not be linked')
    if target.exists() and (target.stat().st_uid!=0 or target.stat().st_mode&0o022 or target.read_bytes()!=value):
        raise SystemExit('Existing verifier differs; inspect before replacement')
for name,value in decoded.items():
    target=base/name
    if not target.exists():
        fd,temporary=tempfile.mkstemp(prefix='.verifier-',dir=base)
        try:
            with os.fdopen(fd,'wb') as stream: stream.write(value);stream.flush();os.fsync(stream.fileno())
            os.chmod(temporary,0o755);os.link(temporary,target)
        finally: Path(temporary).unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=expected[name]: raise SystemExit('Verifier installation checksum mismatch')
environment={**os.environ,'CI_COMMIT_SHA_1':'a'*40,'CI_COMMIT_SHA':'a'*40,'PIPELINE_ID':'verifier-install-check','BUILD_NUMBER':'1'}
result=subprocess.run(['/usr/bin/python3',str(base/'verify_flow.py'),'--inspect'],env=environment,capture_output=True,text=True,check=True,timeout=15)
if json.loads(result.stdout).get('commit')!='a'*40: raise SystemExit('Verifier metadata self-check failed')
print(json.dumps({'installed':True,'entry':str(base/'verify_flow.py'),'file_sha256':expected,
                  'metadata_check':'passed','applications_deployed':False,'production_runtime_read':False}))
'''.replace('EXPECTED',repr(expected))
    result=subprocess.run(ssh_arguments()+['/usr/bin/python3 -c '+shlex.quote(source)],
                          input=json.dumps({name:base64.b64encode(value).decode() for name,value in files.items()}).encode(),
                          capture_output=True,timeout=90)
    print(result.stdout.decode(),end='')
    if result.returncode:
        print('Verify-only installer stopped; no application was deployed.')
        raise SystemExit(result.returncode)


if __name__=='__main__': main()
