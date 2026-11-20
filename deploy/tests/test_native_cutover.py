import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import artifact
from database_tools import PostgresClient
from deploy_release import Deployment
from native_cutover import NativeCutover, CutoverError


@unittest.skipUnless(sys.platform == 'linux', 'Native cutover uses Linux flock and ownership')
class CutoverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        env = self.base / 'independent.env'; env.write_text('# no production settings\n'); env.chmod(0o600)
        self.deployment = Deployment(self.base / 'compose', env, 'blog-test-migrate', 18082, 18002, 'blog.example.com')
        self.commit = 'a' * 40
        self.old_commit = 'b' * 40
        self.source_dir = self.base / 'source'
        for name in artifact.ROOTS: (self.source_dir / name).mkdir(parents=True)
        for name in (*artifact.FILES, *artifact.REQUIRED):
            path = self.source_dir / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# fixture\n')
        (self.source_dir / 'deploy/nginx/https.conf.template').write_text('server __DOMAIN__; port __GATEWAY_PORT__;\n')
        self.directory = artifact.package(self.source_dir, self.commit, self.base / 'artifacts')
        self.deployment.build = Mock()
        self.deployment.compose = Mock()
        self.deployment.start = Mock(return_value={'health': 'UP'})
        self.deployment.backup = Mock()
        self.host = Mock()
        self.host.root = self.base / 'native'; self.host.root.mkdir()
        self.host.backup_root = self.base / 'old-backups'; self.host.backup_root.mkdir()
        self.host.site = self.base / 'nginx.conf'; self.host.site.write_bytes(b'old native config\n')
        self.host.preflight.return_value = self.old_commit, self.host.site.read_bytes()
        self.running = True
        self.host.active.side_effect = lambda: self.running
        self.host.service.side_effect = lambda action: setattr(self, 'running', action == 'start')
        self.full = {'posts': {'count': 1, 'sha256': '1' * 64}, 'alembic_version': {'count': 1, 'sha256': '2' * 64}}
        self.legacy = {'posts': self.full['posts']}
        self.source = Mock(spec=PostgresClient)
        self.source.revision.return_value = '0002'
        self.source.fingerprint.side_effect = lambda **kw: self.legacy if kw.get('legacy_data') else self.full
        self.source.dump.return_value = {'schema': '0002', 'sha256': 'c' * 64}
        self.target = Mock(spec=PostgresClient)
        self.target.revision.side_effect = [None, '0003']
        self.target.restore_empty.return_value = self.full
        self.target.fingerprint.return_value = self.legacy
        self.deployment.postgres_client = Mock(return_value=self.target)
        self.cutover = NativeCutover(self.deployment, self.host, self.source)
        self.web_check = patch('native_cutover.check', return_value={'health': 'UP'})
        self.check = self.web_check.start(); self.addCleanup(self.web_check.stop)

    def journal(self):
        return json.loads((self.cutover.work / 'state.json').read_text())

    def test_success_verifies_import_upgrade_and_public_bytes_before_allowing_flow(self):
        def public_check(*args):
            self.assertFalse(self.running)
            self.assertFalse((self.deployment.root / 'current').exists())
            self.assertFalse((self.deployment.shared / 'traffic-ready.json').exists())
            self.assertEqual(self.journal()['phase'], 'reload-attempted')
            self.assertTrue(self.journal()['traffic_may_have_changed'])
            return {'health': 'UP'}
        self.check.side_effect = public_check
        report = self.cutover.apply(self.directory, self.commit)
        self.assertEqual(report['cutover'], 'passed')
        self.assertFalse(self.running)
        self.assertEqual(self.journal()['phase'], 'complete')
        self.assertTrue(self.deployment.import_verified(self.commit))
        self.assertEqual(self.deployment.previous().name, self.commit)
        ready = json.loads((self.deployment.shared / 'traffic-ready.json').read_text())
        self.assertEqual(ready['project'], self.deployment.project)
        self.target.restore_empty.assert_called_once()
        self.target.fingerprint.assert_called_once_with(legacy_data=True)
        self.host.nginx_reload.assert_called_once()

    def test_import_mismatch_restores_native_before_exposure_and_retains_journal(self):
        self.target.restore_empty.return_value = {}
        with self.assertRaises(CutoverError): self.cutover.apply(self.directory, self.commit)
        self.assertTrue(self.running)
        self.assertEqual(self.host.site.read_bytes(), b'old native config\n')
        self.assertEqual(self.journal()['phase'], 'aborted-before-cutover')
        self.assertFalse(self.journal()['traffic_may_have_changed'])
        self.deployment.start.assert_not_called()
        self.host.nginx_reload.assert_not_called()

    def test_failed_migration_removes_import_gate_and_never_downgrades_data(self):
        self.deployment.start.side_effect = RuntimeError('failed health')
        with self.assertRaises(CutoverError): self.cutover.apply(self.directory, self.commit)
        self.assertTrue(self.running)
        self.assertFalse(self.deployment.import_verified(self.commit))
        self.assertFalse((self.deployment.root / 'current').exists())
        self.assertFalse(any('downgrade' in str(call) for call in self.deployment.compose.call_args_list))

    def test_invalid_nginx_before_reload_restores_configuration_and_native(self):
        self.host.nginx_check.side_effect = [RuntimeError('nginx -t failed'), None]
        with self.assertRaises(CutoverError): self.cutover.apply(self.directory, self.commit)
        self.assertTrue(self.running)
        self.assertEqual(self.host.site.read_bytes(), b'old native config\n')
        self.host.nginx_reload.assert_not_called()
        self.assertFalse(self.journal()['traffic_may_have_changed'])

    def test_reload_timeout_never_resumes_stale_native_database(self):
        self.host.nginx_reload.side_effect = TimeoutError('reload status unknown')
        with self.assertRaisesRegex(CutoverError, 'NEW database'):
            self.cutover.apply(self.directory, self.commit)
        self.assertFalse(self.running)
        self.assertEqual(self.journal()['phase'], 'recovery-required')
        self.assertTrue(self.journal()['traffic_may_have_changed'])
        self.assertIn('18082', self.host.site.read_text())
        self.assertFalse(any('stop' in call.args for call in self.deployment.compose.call_args_list))
        self.assertFalse((self.deployment.shared / 'traffic-ready.json').exists())

    def test_failed_public_check_keeps_new_database_and_blocks_flow(self):
        self.check.side_effect = RuntimeError('public check failed')
        with self.assertRaisesRegex(CutoverError, 'NEW database'):
            self.cutover.apply(self.directory, self.commit)
        self.assertFalse(self.running)
        self.assertFalse((self.deployment.root / 'current').exists())
        self.assertTrue(self.journal()['traffic_may_have_changed'])

    def test_nonempty_target_is_rejected_before_stopping_native(self):
        self.target.revision.side_effect = None; self.target.revision.return_value = '0002'
        with self.assertRaisesRegex(CutoverError, 'not empty'):
            self.cutover.apply(self.directory, self.commit)
        self.host.service.assert_not_called()
        self.target.restore_empty.assert_not_called()

    def test_existing_journal_cannot_be_replayed_over_target_data(self):
        self.cutover.work.mkdir()
        with self.assertRaisesRegex(CutoverError, 'journal'):
            self.cutover.apply(self.directory, self.commit)
        self.host.service.assert_not_called()
        self.deployment.build.assert_not_called()


if __name__ == '__main__': unittest.main()
