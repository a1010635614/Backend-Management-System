"""Linux shell control-flow tests with fake runtime/service commands, never production deployment."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


@unittest.skipUnless(os.name=='posix' and shutil.which('bash'),'Requires Linux Bash; use test-native-release.py')
class NativeReleaseTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid()==0: raise RuntimeError('Run through test-native-release.py to drop root privileges')
        self.work=tempfile.TemporaryDirectory(prefix='vueblog-release-case-')
        self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name)
        self.home=self.root/'application';self.home.mkdir()
        self.old=self.home/'releases'/('b'*40);self.old.mkdir(parents=True)
        (self.home/'incoming').mkdir()
        (self.home/'current').symlink_to(self.old,target_is_directory=True)
        self.marker=self.home/'.current-release';self.marker.write_text('b'*40+'\n')
        self.unit=self.root/'vueblog-test.service'
        self.original_unit='[Service]\nExecStart='+str(self.home)+'/venv/bin/python -m uvicorn app.main:app\n'
        self.unit.write_text(self.original_unit)
        self.bin=self.root/'bin';self.bin.mkdir()
        self.log=self.root/'commands.log'
        self.env={**os.environ,'PATH':str(self.bin)+':'+os.environ['PATH'],'VUEBLOG_TEST_LOG':str(self.log),'VUEBLOG_TEST_FAILURE':'','VUEBLOG_TEST_PIP_ARGS':str(self.root/'pip-args.json')}
        self.write_command('systemctl',"""import os,sys
from pathlib import Path
p=Path(os.environ['VUEBLOG_TEST_LOG']);before=p.read_text() if p.exists() else ''
line='systemctl '+' '.join(sys.argv[1:])
with p.open('a') as f:f.write(line+'\\n')
if sys.argv[1:] not in (['daemon-reload'],['restart','vueblog']):sys.exit(97)
if os.environ.get('VUEBLOG_TEST_FAILURE')=='restart' and sys.argv[1:] == ['restart','vueblog'] and 'systemctl restart' not in before:sys.exit(1)
""")
        self.write_command('chown','')
        self.write_command('sleep','')
        self.write_command('backup',"""import os,sys
with open(os.environ['VUEBLOG_TEST_LOG'],'a') as f:f.write('backup\\n')
sys.exit(1 if os.environ.get('VUEBLOG_TEST_FAILURE')=='backup' else 0)
""")
        self.write_command('curl',"""import os,sys
if '--max-time' not in sys.argv:sys.exit(98)
kind='api' if any('/api/health' in x for x in sys.argv) else 'site'
with open(os.environ['VUEBLOG_TEST_LOG'],'a') as f:f.write('health '+kind+'\\n')
sys.exit(22 if os.environ.get('VUEBLOG_TEST_FAILURE')==kind else 0)
""")
        runtime=self.write_command('runtime',"""import os,sys
step='tests' if sys.argv[1:3]==['-m','unittest'] else 'migrations'
if sys.argv[1:]==['-']:sys.stdin.read()
with open(os.environ['VUEBLOG_TEST_LOG'],'a') as f:f.write(step+'\\n')
sys.exit(1 if os.environ.get('VUEBLOG_TEST_FAILURE')==step else 0)
""")
        pip=self.write_command('pip',"""import json,os,sys
from pathlib import Path
Path(os.environ['VUEBLOG_TEST_PIP_ARGS']).write_text(json.dumps(sys.argv[1:]))
sys.exit(1 if os.environ.get('VUEBLOG_TEST_FAILURE')=='pip' else 0)
""")
        self.env.update(VUEBLOG_TEST_RUNTIME=str(runtime),VUEBLOG_TEST_PIP=str(pip))
        self.write_command('python3',"""import os,shutil,sys
from pathlib import Path
if sys.argv[1:3]==['-m','venv']:
    target=Path(sys.argv[3])/'bin';target.mkdir(parents=True)
    shutil.copy2(os.environ['VUEBLOG_TEST_RUNTIME'],target/'python')
    shutil.copy2(os.environ['VUEBLOG_TEST_PIP'],target/'pip')
else:
    os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
""")
        source=(Path(__file__).parent/'release-native.sh').read_text()
        replacements={'/etc/systemd/system/vueblog.service':str(self.unit),'/etc/vueblog.env':str(self.root/'unused-test.env'),'/usr/local/sbin/vueblog-backup':str(self.bin/'backup'),'/opt/vueblog':str(self.home)}
        for before,after in replacements.items(): source=source.replace(before,after)
        if any(value in source for value in replacements): raise RuntimeError('Unscoped production path in test script')
        self.script=self.root/'release-under-test.sh';self.script.write_text(source)
        self.sha='a'*40
        self.artifact(self.sha)

    def write_command(self,name,source):
        path=self.bin/name
        path.write_text('#!'+sys.executable+'\n'+source)
        path.chmod(0o755)
        return path

    def artifact(self,sha,unsafe=None,link_type=None):
        path=self.home/'incoming'/('blog-'+sha+'.tar.gz')
        with tarfile.open(path,'w:gz') as tar:
            for name,data in (('backend/requirements.txt',b'# fixture'),('backend/app/main.py',b'# fixture'),('frontend/dist/index.html',b'fixture')):
                info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
            if unsafe:
                info=tarfile.TarInfo(unsafe)
                info.size=1;tar.addfile(info,io.BytesIO(b'x'))
            if link_type:
                info=tarfile.TarInfo('backend/linked.py');info.type=link_type
                info.linkname=str(self.root/'outside-sentinel')
                tar.addfile(info)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix('.gz.sha256').write_text(digest+'  '+path.name+'\n')
        return path

    def run_release(self,fail='',sha=None):
        return subprocess.run(['bash',str(self.script)],env={**self.env,'COMMIT_SHA':sha or self.sha,'VUEBLOG_TEST_FAILURE':fail},cwd=self.root,text=True,capture_output=True,timeout=30)

    def assert_previous_unchanged(self):
        self.assertEqual((self.home/'current').resolve(),self.old)
        self.assertEqual(self.unit.read_text(),self.original_unit)
        self.assertEqual(self.marker.read_text(),'b'*40+'\n')

    def test_success_switches_code_service_and_marker(self):
        self.env['PYTHON_PACKAGE_INDEX']='https://mirrors.aliyun.com/pypi/simple/'
        result=self.run_release()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.home/'current').resolve(),self.home/'releases'/self.sha)
        self.assertIn(str(self.home)+'/current/.venv/bin/python',self.unit.read_text())
        self.assertEqual(self.marker.read_text(),self.sha+'\n')
        pip_args=json.loads((self.root/'pip-args.json').read_text())
        self.assertEqual(pip_args[pip_args.index('--index-url')+1],self.env['PYTHON_PACKAGE_INDEX'])

    def test_health_failures_restore_current_unit_and_marker(self):
        for failure in ('api','site','restart'):
            with self.subTest(failure=failure):
                result=self.run_release(failure)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assert_previous_unchanged()
                self.assertIn('previous code/service restored',result.stdout)
                shutil.rmtree(self.home/'releases'/self.sha)
                self.log.unlink(missing_ok=True)

    def test_setup_failures_stop_before_switch(self):
        for failure in ('backup','pip','tests','migrations'):
            with self.subTest(failure=failure):
                result=self.run_release(failure)
                self.assertNotEqual(result.returncode,0)
                self.assert_previous_unchanged()
                self.assertNotIn('systemctl',self.log.read_text() if self.log.exists() else '')
                release=self.home/'releases'/self.sha
                if release.exists(): shutil.rmtree(release)
                self.log.unlink(missing_ok=True)

    def test_checksum_failure_precedes_backup_and_release_creation(self):
        path=self.home/'incoming'/('blog-'+self.sha+'.tar.gz')
        path.write_bytes(path.read_bytes()+b'tampered')
        self.assertNotEqual(self.run_release().returncode,0)
        self.assert_previous_unchanged()
        self.assertFalse((self.home/'releases'/self.sha).exists())
        self.assertFalse(self.log.exists())

    def test_archive_path_traversal_is_rejected(self):
        for name in ('../escaped.txt',str(self.root/'absolute-member.txt')):
            with self.subTest(member=name):
                self.artifact(self.sha,unsafe=name)
                result=self.run_release()
                self.assertNotEqual(result.returncode,0)
                self.assert_previous_unchanged()
                self.assertIn('Unsafe artifact member',result.stdout+result.stderr)
                self.assertFalse((self.root/'absolute-member.txt').exists())
                shutil.rmtree(self.home/'releases'/self.sha)

    def test_parallel_release_is_rejected_by_lock(self):
        import fcntl
        with (self.home/'.native-release.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=self.run_release()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Another release is running',result.stdout)
        self.assert_previous_unchanged();self.assertFalse(self.log.exists())

    def test_archive_links_are_rejected(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE):
            with self.subTest(link_type=kind):
                self.artifact(self.sha,link_type=kind)
                result=self.run_release()
                self.assertNotEqual(result.returncode,0)
                self.assert_previous_unchanged()
                self.assertIn('Unsafe artifact member',result.stdout+result.stderr)
                self.assertFalse((self.home/'releases'/self.sha/'backend').exists())
                shutil.rmtree(self.home/'releases'/self.sha)

    def test_later_failure_restores_previous_native_release(self):
        result=self.run_release()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        unit=self.unit.read_bytes()
        later='c'*40;self.artifact(later)
        result=self.run_release('site',sha=later)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.home/'current').resolve(),self.home/'releases'/self.sha)
        self.assertEqual(self.unit.read_bytes(),unit)
        self.assertEqual(self.marker.read_text(),self.sha+'\n')


if __name__=='__main__': unittest.main()
