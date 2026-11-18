import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from package_native import create_package
from receive_flow_artifact import run_archive


class FlowArchiveReceiveTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.source = self.root / 'source'
        self.extract = self.root / 'extract'
        self.extract.mkdir()
        for name in ('backend/app/main.py', 'backend/migrations/env.py', 'backend/tests/test_api.py',
                     'backend/alembic.ini', 'backend/requirements.txt', 'frontend/dist/index.html', 'deploy/release-native.sh'):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture\n')
        shutil.copyfile(Path(__file__).with_name('stage_native_artifact.py'), self.source / 'deploy/stage_native_artifact.py')
        self.artifacts = create_package(self.source, 'e' * 40)
        self.archive = self.root / 'flow.tgz'

    def pack(self, include_directory=True):
        with tarfile.open(self.archive, 'w:gz') as package:
            if include_directory:
                package.add(self.artifacts, arcname='artifacts')
            else:
                for path in self.artifacts.iterdir():
                    package.add(path, arcname=path.name)

    def test_real_package_verifies_without_publication_and_cleans_extraction(self):
        self.pack()
        with patch.dict(os.environ, {'COMMIT_SHA': 'e' * 40}):
            run_archive(self.archive, verify_only=True, work_parent=self.extract)
        self.assertEqual(list(self.extract.iterdir()), [])

    def test_corrupt_inner_artifact_fails_real_verification(self):
        next(self.artifacts.glob('*.tar.gz')).write_bytes(b'corrupted fixture')
        self.pack()
        with patch.dict(os.environ, {'COMMIT_SHA': 'e' * 40}):
            with self.assertRaises(subprocess.CalledProcessError):
                run_archive(self.archive, verify_only=True, work_parent=self.extract)
        self.assertEqual(list(self.extract.iterdir()), [])

    def test_missing_packaging_directory_stops_before_entry_point(self):
        self.pack(include_directory=False)
        with patch('receive_flow_artifact.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'include the packaging path'):
                run_archive(self.archive, work_parent=self.extract)
            run.assert_not_called()
        self.assertEqual(list(self.extract.iterdir()), [])

    def test_outer_path_traversal_stops_before_entry_point(self):
        with tarfile.open(self.archive, 'w:gz') as package:
            entry = tarfile.TarInfo('../escaped.txt')
            entry.size = 7
            package.addfile(entry, io.BytesIO(b'fixture'))
        with patch('receive_flow_artifact.subprocess.run') as run:
            with self.assertRaises(tarfile.FilterError):
                run_archive(self.archive, work_parent=self.extract)
            run.assert_not_called()
        self.assertFalse((self.extract / 'escaped.txt').exists())
        self.assertEqual(list(self.extract.iterdir()), [])

    def test_publication_dispatch_uses_packaged_entry_and_propagates_failure(self):
        self.pack()
        with patch('receive_flow_artifact.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'fixture')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                run_archive(self.archive, work_parent=self.extract)
        args, kwargs = run.call_args
        self.assertEqual(Path(args[0][1]).name, 'stage_native_artifact.py')
        self.assertEqual(Path(args[0][2]).name, 'artifacts')
        self.assertNotIn('--verify-only', args[0])
        self.assertTrue(kwargs['check'])
        self.assertEqual(list(self.extract.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
