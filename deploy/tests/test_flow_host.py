from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import flow_host


class FlowHostTests(unittest.TestCase):
    def fixture(self):
        return {'CI_COMMIT_SHA': 'a' * 40, 'PIPELINE_ID': '1456575', 'BUILD_NUMBER': '17'}

    def test_inspect_cannot_unpack_or_deploy(self):
        with patch.object(subprocess, 'run') as invoke:
            metadata = flow_host.run(self.fixture(), inspect=True)
        invoke.assert_not_called()
        self.assertEqual(metadata['archive'], '/opt/vueblog/flow/1456575/17/blog-native.tgz')

    def test_full_source_sha_is_passed_to_versioned_receiver_in_separate_arguments(self):
        with patch.object(subprocess, 'run') as invoke:
            metadata = flow_host.run(self.fixture())
        command = invoke.call_args.args[0]
        self.assertEqual(command[-2:], ['--commit', 'a' * 40])
        self.assertEqual(Path(command[1]), Path(flow_host.__file__).resolve().with_name('receive.py'))
        self.assertNotIn('/usr/local/sbin/vueblog-flow-deploy', command)
        self.assertEqual(metadata['result'], 'deployed')

    def test_short_missing_encoded_and_ambiguous_commits_fail_before_invocation(self):
        for value in ('', 'a' * 8, 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=='):
            fixture = self.fixture(); fixture['CI_COMMIT_SHA'] = value
            with self.subTest(value=value), patch.object(subprocess, 'run') as invoke, self.assertRaises(ValueError):
                flow_host.run(fixture)
            invoke.assert_not_called()
        fixture = {**self.fixture(), 'CI_COMMIT_SHA_1': 'b' * 40}
        with self.assertRaises(ValueError): flow_host.context(fixture)

    def test_numbered_source_and_bounded_identifiers_are_supported(self):
        fixture = self.fixture(); fixture['CI_COMMIT_SHA_1'] = fixture.pop('CI_COMMIT_SHA')
        self.assertEqual(flow_host.context(fixture)['commit'], 'a' * 40)
        for key, value in [('PIPELINE_ID', '../wrong'), ('BUILD_NUMBER', '17/../../wrong'), ('BUILD_NUMBER', '0')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                flow_host.context({**fixture, key: value})


if __name__ == '__main__': unittest.main()
