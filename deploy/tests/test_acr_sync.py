import contextlib
import base64
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

spec = importlib.util.spec_from_file_location('acr_sync', Path(__file__).resolve().parents[1] / 'sync_acr_images.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class AcrSynchronizationTests(unittest.TestCase):
    def test_only_an_existing_unauthenticated_loopback_proxy_can_be_used(self):
        for value, expected in [('http://127.0.0.1:7890', 'http://127.0.0.1:7890'),
                                ('http://attacker.invalid:7890', None),
                                ('http://fixture-user:fixture-secret@127.0.0.1:7890', None)]:
            with patch.object(sync, 'getproxies', return_value={'https': value}):
                self.assertEqual(sync.loopback_proxy(), expected)

    def jwt(self, grants):
        payload = base64.urlsafe_b64encode(json.dumps({'access': grants, 'sub': 'fixture-private-identity'}).encode()).decode().rstrip('=')
        return 'fixture-header.' + payload + '.fixture-signature'

    def test_anonymous_or_wrong_repository_grants_stop_before_registry_writes(self):
        for grants in ([], [{'type': 'repository', 'name': 'another-space/private', 'actions': ['pull', 'push']}],
                       [{'type': 'repository', 'name': 'kongqi-blog/base-python', 'actions': ['pull']}]):
            token = self.jwt(grants)
            with self.assertRaises(sync.SyncError) as caught:
                sync.require_repository_grants(token, 'kongqi-blog/base-python')
            self.assertEqual(caught.exception.code, 'REPOSITORY_PERMISSION_MISSING')
            self.assertNotIn(token, str(caught.exception))
            self.assertNotIn('fixture-private-identity', str(caught.exception))

    def test_exact_repository_pull_and_push_grants_are_accepted(self):
        token = self.jwt([{'type': 'repository', 'name': 'kongqi-blog/base-python', 'actions': ['push', 'pull']}])
        sync.require_repository_grants(token, 'kongqi-blog/base-python')

    def test_opaque_tokens_still_require_normal_registry_verification(self):
        sync.require_repository_grants('fixture-short-lived-token', 'kongqi-blog/base-python')

    def challenge(self, realm='https://dockerauth.cn-hangzhou.aliyuncs.com/auth'):
        return urllib.error.HTTPError('https://' + sync.REGISTRY + '/v2/', 401, 'fixture challenge',
            {'WWW-Authenticate': 'Bearer realm="' + realm + '",service="' + sync.REGISTRY + '"'}, None)

    def test_token_exchange_rejects_another_realm_before_sending_credentials(self):
        opener = Mock()
        opener.open.side_effect = self.challenge('https://attacker.invalid/auth')
        with patch.object(sync.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(sync.SyncError): sync.registry_token('fixture-user', 'fixture-secret', 'kongqi-blog/base-python')
        self.assertEqual(opener.open.call_count, 1)

    def test_token_exchange_uses_https_basic_header_and_one_repository_scope(self):
        opener = Mock()
        opener.open.side_effect = [self.challenge(), io.BytesIO(b'{"token":"fixture-short-lived-token"}')]
        with patch.object(sync.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(sync.registry_token('fixture-user', 'fixture-secret', 'kongqi-blog/base-python'), 'fixture-short-lived-token')
        request = opener.open.call_args_list[1].args[0]
        self.assertTrue(request.full_url.startswith('https://dockerauth.cn-hangzhou.aliyuncs.com/auth?'))
        self.assertNotIn('fixture-user', request.full_url)
        self.assertNotIn('fixture-secret', request.full_url)
        self.assertIn('kongqi-blog%2Fbase-python', request.full_url)
        self.assertTrue(request.headers['Authorization'].startswith('Basic '))

    def test_bad_registry_credentials_are_classified_without_echoing_them(self):
        opener = Mock()
        opener.open.side_effect = [self.challenge(), urllib.error.HTTPError('https://dockerauth.cn-hangzhou.aliyuncs.com/auth',
            401, 'fixture-secret must not appear', {}, None)]
        with patch.object(sync.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(sync.SyncError) as caught:
                sync.registry_token('fixture-user', 'fixture-secret', 'kongqi-blog/base-python')
        self.assertEqual(caught.exception.code, 'AUTH_REJECTED')
        self.assertNotIn('fixture-secret', str(caught.exception))

    def test_transport_classification_does_not_echo_secret_urls_or_messages(self):
        for raw, expected in [(b'UNAUTHORIZED password=fixture-secret https://host/?signature=fixture-secret', 'AUTH_REJECTED'),
                              (b'x509: unknown certificate fixture-secret', 'TLS_FAILURE'),
                              (b'context deadline exceeded fixture-secret', 'NETWORK_TIMEOUT'),
                              (b'opaque fixture-secret', 'TRANSPORT_FAILURE')]:
            with self.subTest(expected=expected):
                self.assertEqual(sync.transport_failure(raw), expected)
                self.assertNotIn('fixture-secret', sync.transport_failure(raw))

    def plan(self):
        return {'registry': sync.REGISTRY, 'namespace': 'kongqi-blog', 'images': [
            {'name': name, 'digest': 'sha256:' + str(index) * 64, 'platform': 'linux/amd64',
             'source': 'index.docker.io/library/' + name + '@sha256:' + str(index) * 64,
             'destination': sync.REGISTRY + '/kongqi-blog/base-' + name + ':' + tag}
            for index, (name, tag) in enumerate(sync.TAGS.items(), 1)]}

    def test_plan_rejects_another_registry_source_platform_or_duplicate_before_login(self):
        for field, value in [('registry', 'attacker.invalid'), ('source', 'attacker.invalid/library/python@sha256:' + '1' * 64),
                             ('platform', 'linux/arm64'), ('destination', sync.REGISTRY + '/another-space/python:latest')]:
            plan = self.plan()
            if field == 'registry': plan[field] = value
            else: plan['images'][0][field] = value
            with self.subTest(field=field), patch.object(sync, 'credentials', side_effect=AssertionError('no login')):
                with self.assertRaises(sync.SyncError): sync.apply(plan, Path(sys.executable))
        plan = self.plan(); plan['images'][1] = plan['images'][0]
        with self.assertRaises(sync.SyncError): sync.validate_plan(plan)

    def layouts(self, root, plan):
        for image in plan['images']:
            directory = root / '.local/acr-oci' / image['name']
            blobs = directory / 'blobs/sha256'; blobs.mkdir(parents=True)
            def blob(data):
                digest = hashlib.sha256(data).hexdigest()
                (blobs / digest).write_bytes(data)
                return {'digest': 'sha256:' + digest, 'size': len(data)}
            config = blob(json.dumps({'os': 'linux', 'architecture': 'amd64', 'rootfs': {'diff_ids': []}}).encode())
            layer = blob(b'isolated OCI descriptor fixture')
            manifest = blob(json.dumps({'schemaVersion': 2, 'config': config, 'layers': [layer]}).encode())
            (directory / 'index.json').write_text(json.dumps({'manifests': [manifest]}))
            image.update(digest=manifest['digest'], config_digest=config['digest'], oci_directory=str(directory),
                         source='index.docker.io/library/' + image['name'] + '@' + manifest['digest'])

    def run_fixture(self, fail=False, wrong_digest=False, oci=False):
        configs = []
        calls = []
        plan = self.plan()
        digests = {image['destination']: image['digest'] for image in plan['images']}
        def command(binary, arguments, environment, phase, **kwargs):
            directory = Path(environment['DOCKER_CONFIG'])
            self.assertTrue(directory.is_dir())
            configs.append(directory)
            calls.append(arguments)
            self.assertNotIn('fixture-password', ' '.join(arguments))
            config = json.loads((directory / 'config.json').read_text())
            self.assertEqual(config['auths'][sync.REGISTRY]['registrytoken'], 'fixture-short-lived-token')
            self.assertNotIn('fixture-password', json.dumps(config))
            if phase.startswith('copying-'):
                self.assertIn('--no-clobber', arguments)
                if fail: raise sync.SyncError('simulated network failure')
            if phase.startswith('checking-existing-'):
                raise sync.SyncError('fixture empty repository', code='NOT_FOUND')
            if phase.startswith('verifying-'):
                return 'sha256:' + 'f' * 64 if wrong_digest else digests[arguments[-1]]
            return ''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root / '.local').mkdir()
            if oci:
                self.layouts(root, plan)
                digests.update({image['destination']: image['digest'] for image in plan['images']})
            output = io.StringIO()
            with (patch.object(sync, 'ROOT', root),
                  patch.object(sync, 'credentials', return_value=('fixture-user', 'fixture-password')),
                  patch.object(sync, 'registry_token', return_value='fixture-short-lived-token'),
                  patch.object(sync, 'command', side_effect=command), contextlib.redirect_stdout(output)):
                if fail or wrong_digest:
                    with self.assertRaises(sync.SyncError): sync.apply(plan, Path(sys.executable))
                    result = None
                else:
                    result = sync.apply(plan, Path(sys.executable))
            self.assertTrue(configs)
            self.assertTrue(all(not path.exists() for path in configs))
            self.assertNotIn('fixture-password', output.getvalue())
            self.assertNotIn('fixture-user', output.getvalue())
            return result, calls

    def test_copy_is_source_bound_and_credentials_are_removed_after_success(self):
        result, calls = self.run_fixture()
        self.assertTrue(result['temporary_credentials_removed'])
        self.assertEqual(len(result['images']), 3)
        self.assertTrue(all(image['verified'] and '@sha256:' in image['ci_reference'] for image in result['images']))
        self.assertEqual(sum(arguments[0] == 'copy' for arguments in calls), 3)
        self.assertNotIn('fixture-password', json.dumps(result))

    def test_interrupted_copy_still_removes_private_credential_directory(self):
        self.run_fixture(fail=True)

    def test_existing_wrong_tag_is_rejected_without_overwriting_it(self):
        self.run_fixture(wrong_digest=True)

    def test_verified_oci_upload_checks_remote_tag_and_preserves_source_digest(self):
        result, calls = self.run_fixture(oci=True)
        self.assertTrue(result['temporary_credentials_removed'])
        self.assertEqual(sum(arguments[0] == 'push' for arguments in calls), 3)
        self.assertEqual(sum(arguments[0] == 'copy' for arguments in calls), 0)
        self.assertEqual(sum(arguments[0] == 'digest' for arguments in calls), 6)

    def test_tampered_oci_blob_is_rejected_before_requesting_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            plan = self.plan(); self.layouts(root, plan)
            image = plan['images'][0]
            config = Path(image['oci_directory']) / 'blobs/sha256' / image['config_digest'].split(':', 1)[1]
            config.write_bytes(b'corrupted fixture')
            with (patch.object(sync, 'ROOT', root),
                  patch.object(sync, 'credentials', side_effect=AssertionError('no credential input')),
                  patch.object(sync, 'command', side_effect=AssertionError('no registry command'))):
                with self.assertRaises(sync.SyncError): sync.apply(plan, Path(sys.executable))


if __name__ == '__main__':
    unittest.main()
