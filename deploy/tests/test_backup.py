from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from database_tools import DatabaseError
from backup import prune_verified
from restore_drill import DisposablePostgres


@unittest.skipUnless(hasattr(os, 'getuid'), 'POSIX ownership is part of the backup contract')
class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def backup(self, number, age, checked=True):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        stamp = now - timedelta(days=age)
        path = self.root / ('blog-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + f'-{number:012x}.dump')
        data = b'PGDMP' + b'fixture' * 20
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        metadata = {'format': 1, 'archive': path.name, 'bytes': len(data), 'sha256': digest, 'schema': '0003'}
        path.with_suffix('.dump.json').write_text(json.dumps(metadata))
        path.with_suffix('.dump.sha256').write_text(digest + '  ' + path.name + '\n')
        if checked:
            path.with_suffix('.dump.restore.json').write_text(json.dumps({'sha256': digest, 'isolated_restore': True}))
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
        return path

    def test_retention_preserves_two_restore_points_and_all_unverified_backups(self):
        files = [self.backup(index, age) for index, age in enumerate((15, 14, 13, 12), 1)]
        unverified = self.backup(5, 90, checked=False)
        removed = prune_verified(self.root, 7, now=datetime(2026, 11, 20, tzinfo=timezone.utc))
        self.assertEqual(removed, 2)
        self.assertEqual([path.exists() for path in files], [False, False, True, True])
        self.assertTrue(unverified.exists())

    def disposable(self):
        container = DisposablePostgres(self.root)
        container.work = self.root / '.restore-fixture'
        container.work.mkdir()
        (container.work / 'data').mkdir()
        container.attempted = True
        return container

    def test_uncertain_container_creation_retains_the_bind_directory(self):
        container = self.disposable()
        failed = subprocess.CompletedProcess([], 1, stdout=b'', stderr=b'fixture daemon unavailable')
        with patch('restore_drill.subprocess.run', side_effect=[failed, failed]) as run:
            with self.assertRaises(DatabaseError): container.__exit__(None, None, None)
        self.assertTrue(container.work.exists())
        self.assertFalse(any('rm' in call.args[0] for call in run.call_args_list))

    def test_a_name_collision_never_removes_another_container(self):
        container = self.disposable()
        result = subprocess.CompletedProcess([], 0, stdout=b'another-job\n')
        with patch('restore_drill.subprocess.run', return_value=result) as run:
            with self.assertRaises(DatabaseError): container.__exit__(None, None, None)
        self.assertTrue(container.work.exists())
        self.assertEqual(run.call_count, 1)

    def test_verified_container_cleanup_precedes_directory_removal(self):
        container = self.disposable()
        directory = container.work
        results = [subprocess.CompletedProcess([], 0, stdout=(container.identifier + '\n').encode()),
                   subprocess.CompletedProcess([], 0, stdout=b'')]
        with patch('restore_drill.subprocess.run', side_effect=results) as run:
            container.__exit__(None, None, None)
        self.assertIn('rm', run.call_args_list[1].args[0])
        self.assertFalse(directory.exists())


if __name__ == '__main__':
    unittest.main()
