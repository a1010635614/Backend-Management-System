"""Check export failure gates with a client that rejects Compose/network APIs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CLIENT = r'''
import io
import json
import os
from pathlib import Path
import sys
import tarfile

args = sys.argv[1:]
failure = os.environ.get('FLOW_TEST_FAILURE', '')
if Path(sys.argv[0]).name == 'git':
    if args == ['rev-parse', 'HEAD']: print('c' * 40)
    elif args == ['rev-parse', '--show-prefix']: print('')
    elif args[:1] == ['diff']: pass
    elif args[:1] == ['archive']: sys.stdout.buffer.write(b'fake source stream')
    else: raise SystemExit(98)
    raise SystemExit(0)
with open(os.environ['FLOW_TEST_DOCKER_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
if args[0] == 'info': raise SystemExit(1 if failure == 'daemon' else 0)
elif args[0] == 'build':
    sys.stdin.buffer.read()
    raise SystemExit(1 if failure == 'build' else 0)
elif args[0] == 'run':
    if failure == 'corrupt-stream':
        sys.stdout.buffer.write(b'not an archive')
        raise SystemExit(0)
    commit = 'c' * 40
    names = ['manifest.json', 'blog-' + commit + '.tar.gz', 'blog-' + commit + '.tar.gz.sha256',
             'release-native.sh', 'stage_native_artifact.py']
    if failure == 'missing-file': names.remove('stage_native_artifact.py')
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
        for name in names:
            member = tarfile.TarInfo(name);member.size = 7
            archive.addfile(member, io.BytesIO(b'fixture'))
    raise SystemExit(42 if failure == 'export-exit' else 0)
else:
    print('flow not support: ' + args[0], file=sys.stderr)
    raise SystemExit(98)
'''


@unittest.skipUnless(os.name == 'posix', 'Flow shell checks require Linux')
class FlowBuildControlTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.bin = self.root / 'bin';self.bin.mkdir()
        for name in ('git', 'docker'):
            path = self.bin / name
            path.write_text('#!' + sys.executable + '\n' + CLIENT)
            path.chmod(0o755)
        deploy = self.root / 'deploy';deploy.mkdir()
        shutil.copyfile(Path(__file__).with_name('build-flow.sh'), deploy / 'build-flow.sh')
        self.log = self.root / 'docker.jsonl'

    def run_build(self, failure='', settings=None):
        env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
               'COMMIT_SHA': 'c' * 40, 'FLOW_TEST_FAILURE': failure, 'FLOW_TEST_DOCKER_LOG': str(self.log),
               'PYTHON_BUILD_IMAGE': 'python:3.12-slim-bookworm', 'NODE_BUILD_IMAGE': 'node:22-bookworm-slim',
               'POSTGRES_TEST_IMAGE': 'postgres:16-bookworm', 'PYTHON_PACKAGE_INDEX': 'https://pypi.org/simple'}
        env.update(settings or {})
        result = subprocess.run(['bash', 'deploy/build-flow.sh'], cwd=self.root, env=env,
                                text=True, capture_output=True, timeout=30)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def assert_no_export(self):
        self.assertFalse((self.root / 'artifacts').exists())
        self.assertEqual(list(self.root.glob('.flow-export.*')), [])

    def test_unavailable_daemon_stops_before_build(self):
        result, calls = self.run_build('daemon')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [['info']])
        self.assert_no_export()

    def test_build_failure_prevents_export(self):
        result, calls = self.run_build('build')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('run', [call[0] for call in calls])
        self.assert_no_export()

    def test_failed_exporter_exit_is_detected_even_with_complete_tar_stream(self):
        result, _ = self.run_build('export-exit')
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_export()

    def test_corrupt_tar_stream_never_publishes_partial_artifact(self):
        result, _ = self.run_build('corrupt-stream')
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_export()

    def test_missing_required_file_stops_before_export_is_published(self):
        result, _ = self.run_build('missing-file')
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_export()

    def test_success_uses_only_supported_build_and_run_operations(self):
        result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call[0] for call in calls], ['info', 'build', 'run'])
        self.assertEqual(len(list((self.root / 'artifacts').iterdir())), 5)
        self.assertEqual(list(self.root.glob('.flow-export.*')), [])

    def test_configured_sources_are_passed_to_the_build(self):
        settings = {'PYTHON_BUILD_IMAGE': 'public.ecr.aws/docker/library/python:3.12-slim-bookworm',
                    'NODE_BUILD_IMAGE': 'public.ecr.aws/docker/library/node:22-bookworm-slim',
                    'POSTGRES_TEST_IMAGE': 'public.ecr.aws/docker/library/postgres:16-bookworm',
                    'PYTHON_PACKAGE_INDEX': 'https://mirrors.aliyun.com/pypi/simple/'}
        result, calls = self.run_build(settings=settings)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build = next(call for call in calls if call[0] == 'build')
        for name, value in settings.items(): self.assertIn(name + '=' + value, build)
        self.assertIn('COMMIT_SHA=' + 'c' * 40, build)

    def test_old_alpine_setting_fails_before_image_build(self):
        result, calls = self.run_build(settings={'POSTGRES_TEST_IMAGE': 'postgres:16-alpine'})
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('build', [call[0] for call in calls])
        self.assert_no_export()


if __name__ == '__main__': unittest.main()
