import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import artifact


@unittest.skipUnless(sys.platform == 'linux', 'Linux ownership, symlinks and flock are deployment requirements')
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        from deploy_release import Deployment, DeployError
        self.error = DeployError
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.envfile = self.base / 'test.env'
        self.envfile.write_text('# independent fixture; no production credentials\n')
        self.envfile.chmod(0o600)
        self.deployment = Deployment(self.base / 'host', self.envfile, 'blog-test-release', 18082, 18002, 'localhost')
        self.source = self.base / 'source'
        for name in artifact.ROOTS:
            (self.source / name).mkdir(parents=True)
        for name in (*artifact.FILES, *artifact.REQUIRED):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n')
        for frontend in ('frontend-web', 'frontend-admin'):
            path = self.source / frontend / 'dist/assets/app-123.js'
            path.parent.mkdir()
            path.write_text('fixture content')
        self.commit = 'a' * 40
        self.directory = artifact.package(self.source, self.commit, self.base / 'artifacts')
        self.deployment.compose = Mock()
        self.deployment.backup = Mock()

    def test_first_release_does_not_silently_initialize_empty_database(self):
        with self.assertRaises(self.error):
            self.deployment.deploy(self.directory, self.commit)
        self.deployment.compose.assert_not_called()

    def test_health_failure_restores_previous_application_without_downgrading_data(self):
        previous_commit = 'b' * 40
        previous_artifacts = artifact.package(self.source, previous_commit, self.base / 'previous-artifacts')
        previous = self.deployment.stage(previous_artifacts, previous_commit)
        (self.deployment.root / 'current').symlink_to(previous)
        (self.deployment.root / '.current-release').write_text(previous_commit)
        self.deployment.start = Mock(side_effect=[RuntimeError('health failed'), {'health': 'UP'}])
        with self.assertRaises(self.error):
            self.deployment.deploy(self.directory, self.commit)
        self.assertEqual(self.deployment.previous(), previous)
        self.assertEqual([call.args[0].name for call in self.deployment.start.call_args_list], [self.commit, previous_commit])
        self.assertEqual((self.deployment.root / '.current-release').read_text(), previous_commit)
        self.assertFalse(any('downgrade' in str(call) for call in self.deployment.compose.call_args_list))

    def test_success_publishes_source_marker_only_after_health_passes(self):
        def start(release):
            self.assertFalse((self.deployment.root / 'current').exists())
            self.assertFalse((self.deployment.root / '.current-release').exists())
            return {'health': 'UP'}
        self.deployment.start = start
        self.deployment.deploy(self.directory, self.commit, initialize_empty=True)
        self.assertEqual(self.deployment.previous().name, self.commit)
        self.assertEqual((self.deployment.root / '.current-release').read_text(), self.commit + '\n')
        self.deployment.backup.assert_called_once()

    def test_new_install_failure_stops_application_but_preserves_database(self):
        self.deployment.start = Mock(side_effect=RuntimeError('failed'))
        with self.assertRaises(self.error):
            self.deployment.deploy(self.directory, self.commit, initialize_empty=True)
        self.assertFalse((self.deployment.root / 'current').exists())
        stopped = [call.args for call in self.deployment.compose.call_args_list if 'stop' in call.args]
        self.assertEqual(len(stopped), 1)
        self.assertNotIn('postgres', stopped[0])
        self.assertNotIn('redis', stopped[0])

    def test_static_assets_are_retained_and_name_collision_blocks_release(self):
        release = self.deployment.stage(self.directory, self.commit)
        self.deployment.assets(release)
        retained = self.deployment.shared / 'web-assets/app-123.js'
        self.assertEqual(retained.read_text(), 'fixture content')
        (release / 'frontend-web/dist/assets/app-123.js').write_text('different content')
        with self.assertRaises(self.error):
            self.deployment.assets(release)
        self.assertEqual(retained.read_text(), 'fixture content')

    def test_runtime_environment_must_not_be_group_or_world_readable(self):
        from deploy_release import Deployment
        self.envfile.chmod(0o640)
        with self.assertRaises(self.error):
            Deployment(self.base / 'other', self.envfile, 'blog-test-release', 18082, 18002, 'localhost')

    def test_import_marker_is_bound_to_source_and_project_and_is_private(self):
        from database_tools import write_json
        marker = self.deployment.shared / 'database-import-verified.json'
        marker.write_text('{}')
        self.assertFalse(self.deployment.import_verified(self.commit))
        value = {'format': 1, 'commit': self.commit, 'project': self.deployment.project,
                 'source_schema': '0002', 'source_commit': 'b' * 40, 'archive_sha256': 'c' * 64}
        write_json(marker, value)
        self.assertTrue(self.deployment.import_verified(self.commit))
        self.assertFalse(self.deployment.import_verified('d' * 40))
        marker.chmod(0o640)
        self.assertFalse(self.deployment.import_verified(self.commit))

    def test_runner_environment_cannot_override_runtime_credentials_or_docker_host(self):
        release = self.deployment.releases / self.commit
        with patch.dict(os.environ, {'DATABASE_URL': 'wrong-fixture', 'MAIL_PASSWORD': 'wrong-fixture',
                                     'DOCKER_HOST': 'tcp://wrong-fixture:2375', 'GATEWAY_PORT': '9999'}):
            command, env = self.deployment.compose_settings(release)
        for name in ('DATABASE_URL', 'MAIL_PASSWORD', 'DOCKER_HOST'):
            self.assertNotIn(name, env)
        self.assertEqual(env['GATEWAY_PORT'], str(self.deployment.gateway_port))
        self.assertIn(str(self.envfile), command)


if __name__ == '__main__':
    unittest.main()
