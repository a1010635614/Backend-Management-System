"""Check Flow failure gates with fake clients; this does not validate a Docker daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CLIENT = r'''
import json
import os
from pathlib import Path
import sys

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
elif args[0] == 'compose': pass
elif args[0] == 'build': sys.stdin.buffer.read()
elif args[0] == 'create': print(('a' if any('node:' in value for value in args) else 'b') * 64)
elif args[0] == 'start': pass  # Client success must not hide a failed container process.
elif args[0] == 'inspect':
    failed = (failure == 'frontend' and args[-1] == 'a' * 64) or (failure == 'package' and args[-1] == 'b' * 64)
    print('exited 42' if failed else 'exited 0')
elif args[0] == 'cp':
    if args[1] == '-': sys.stdin.buffer.read()
    if args[-1] == '-':
        if failure == 'dist-stream': raise SystemExit(1)
        sys.stdout.buffer.write(b'fake dist stream')
    if args[-1] == 'artifacts/': Path('artifacts/fixture').write_text('copied')
elif args[0] == 'rm': pass
else: raise SystemExit(98)
'''


@unittest.skipUnless(os.name == 'posix', 'Flow shell checks require Linux')
class FlowBuildControlTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('git', 'docker'):
            path = self.bin / name
            path.write_text('#!' + sys.executable + '\n' + CLIENT)
            path.chmod(0o755)
        deploy = self.root / 'deploy'
        deploy.mkdir()
        shutil.copyfile(Path(__file__).with_name('build-flow.sh'), deploy / 'build-flow.sh')
        (deploy / 'test-postgres.sh').write_text('if [[ "${FLOW_TEST_FAILURE:-}" == postgres ]]; then exit 7; fi\nprintf "%s\\n%s\\n%s\\n" "$PYTHON_BUILD_IMAGE" "$POSTGRES_TEST_IMAGE" "$PYTHON_PACKAGE_INDEX" > postgres-images.txt\n')
        self.log = self.root / 'docker.jsonl'

    def run_build(self, failure='', images=None):
        env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
               'COMMIT_SHA': 'c' * 40, 'FLOW_TEST_FAILURE': failure, 'FLOW_TEST_DOCKER_LOG': str(self.log)}
        env.update(images or {})
        result = subprocess.run(['bash', 'deploy/build-flow.sh'], cwd=self.root, env=env,
                                text=True, capture_output=True, timeout=30)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def assert_no_artifact(self):
        self.assertFalse((self.root / 'artifacts').exists())

    def test_unavailable_daemon_stops_before_build_or_container_creation(self):
        result, calls = self.run_build('daemon')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [['info']])
        self.assert_no_artifact()

    def test_database_failure_stops_before_frontend_and_packaging(self):
        result, calls = self.run_build('postgres')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[0] == 'create' for call in calls))
        self.assert_no_artifact()

    def test_frontend_process_failure_is_detected_even_when_start_returns_success(self):
        result, calls = self.run_build('frontend')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(call[0] == 'create' for call in calls), 1)
        self.assertEqual(calls[-1], ['rm', '--force', 'a' * 64])
        self.assert_no_artifact()

    def test_package_process_failure_prevents_artifact_export_and_removes_owned_containers(self):
        result, calls = self.run_build('package')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-1], ['rm', '--force', 'a' * 64, 'b' * 64])
        self.assert_no_artifact()

    def test_failed_dist_stream_stops_before_package_start(self):
        result, calls = self.run_build('dist-stream')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(['start', '--attach', 'b' * 64], calls)
        self.assertEqual(calls[-1], ['rm', '--force', 'a' * 64, 'b' * 64])
        self.assert_no_artifact()

    def test_success_exports_artifact_and_only_removes_created_containers(self):
        result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / 'artifacts/fixture').read_text(), 'copied')
        self.assertEqual(calls[-1], ['rm', '--force', 'a' * 64, 'b' * 64])

    def test_configured_image_sources_reach_tools_frontend_and_database_checks(self):
        images = {'PYTHON_BUILD_IMAGE': 'public.ecr.aws/docker/library/python:3.12-slim-bookworm',
                  'NODE_BUILD_IMAGE': 'public.ecr.aws/docker/library/node:22-bookworm-slim',
                  'POSTGRES_TEST_IMAGE': 'public.ecr.aws/docker/library/postgres:16-alpine',
                  'PYTHON_PACKAGE_INDEX': 'https://mirrors.aliyun.com/pypi/simple/'}
        result, calls = self.run_build(images=images)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build = next(call for call in calls if call[0] == 'build')
        self.assertIn('PYTHON_BUILD_IMAGE=' + images['PYTHON_BUILD_IMAGE'], build)
        web = next(call for call in calls if call[0] == 'create')
        self.assertIn(images['NODE_BUILD_IMAGE'], web)
        self.assertEqual((self.root / 'postgres-images.txt').read_text().splitlines(),
                         [images['PYTHON_BUILD_IMAGE'], images['POSTGRES_TEST_IMAGE'], images['PYTHON_PACKAGE_INDEX']])


if __name__ == '__main__': unittest.main()
