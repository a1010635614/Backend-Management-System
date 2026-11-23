import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install_alidns as installer


FAKE_HOOK=b'''class HookError(RuntimeError): pass
class Client:
    def __init__(self,credentials): self.credentials=credentials
    def challenge_records(self):
        if self.credentials.get('access_key_id')=='reject': raise HookError('read permission rejected')
        return []
def client_from_credentials(value): return Client(value)
def nameservers(): return ['ns.fixture.example']
'''


class InstallationPlanTests(unittest.TestCase):
    def test_plan_does_not_read_files_or_transmit_credentials(self):
        with patch.object(Path,'stat',side_effect=AssertionError('no reads')):
            result=installer.plan()
        self.assertEqual(result['credentials'],'/etc/letsencrypt/alidns-hook.json')
        self.assertIs(result['dns_records_changed'],False)
        self.assertIs(result['renewal_configuration_changed'],False)


@unittest.skipUnless(os.name=='posix' and os.geteuid()==0,'root POSIX installation checks require the Linux verifier')
class RootInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.code=self.base/'code/alidns_hook.py'
        self.config=self.base/'etc/alidns-hook.json'
        self.state=self.base/'state'
        for key,value in [('CODE',self.code),('CONFIG',self.config),('STATE',self.state),('RELOAD',self.code.with_name('reload-nginx.sh'))]:
            patcher=patch.object(installer,key,value);patcher.start();self.addCleanup(patcher.stop)
        self.credentials={'access_key_id':'fixture-access-key','access_key_secret':'fixture-secret-only'}

    def test_read_permission_failure_happens_before_any_publication(self):
        with self.assertRaises(installer.InstallError): installer.install(FAKE_HOOK,{'access_key_id':'reject'})
        self.assertFalse(self.config.exists())
        self.assertFalse(self.code.exists())
        self.assertFalse(self.state.exists())

    def test_installation_is_private_source_bound_and_identical_reruns_are_safe(self):
        result=installer.install(FAKE_HOOK,self.credentials)
        self.assertTrue(result['installed'])
        self.assertEqual(self.config.stat().st_mode&0o777,0o600)
        self.assertEqual(self.state.stat().st_mode&0o777,0o700)
        self.assertEqual(self.code.stat().st_mode&0o777,0o755)
        self.assertEqual(self.code.read_bytes(),FAKE_HOOK)
        self.assertIs(result['dns_records_changed'],False)
        self.assertEqual(installer.install(FAKE_HOOK,self.credentials)['hook_sha256'],result['hook_sha256'])

    def test_existing_credentials_block_hook_publication_and_are_never_overwritten(self):
        self.config.parent.mkdir(mode=0o755)
        original=b'{"other":"fixture-not-to-replace"}\n'
        self.config.write_bytes(original);self.config.chmod(0o600)
        with self.assertRaises(installer.InstallError): installer.install(FAKE_HOOK,self.credentials)
        self.assertEqual(self.config.read_bytes(),original)
        self.assertFalse(self.code.exists())

    def test_symlink_config_never_changes_the_destination(self):
        self.config.parent.mkdir(mode=0o755)
        target=self.base/'keep.json';target.write_text('preserve')
        self.config.symlink_to(target)
        with self.assertRaises(installer.InstallError): installer.install(FAKE_HOOK,self.credentials)
        self.assertEqual(target.read_text(),'preserve')
        self.assertFalse(self.code.exists())


if __name__=='__main__': unittest.main()
