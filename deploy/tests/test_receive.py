import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import artifact
import receive
import verify_flow


class ReceiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / 'source'
        for name in artifact.ROOTS:
            (source / name).mkdir(parents=True)
        for name in (*artifact.FILES, *artifact.REQUIRED):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n')
        self.commit = 'a' * 40
        self.artifacts = artifact.package(source, self.commit, self.root / 'artifacts')
        self.outer = self.root / 'flow.tgz'

    def pack(self, extra=None):
        with tarfile.open(self.outer, 'w:gz') as tar:
            tar.add(self.artifacts, arcname='./artifacts')
            if extra is not None:
                tar.addfile(extra, io.BytesIO(b'x') if extra.isfile() else None)

    def test_valid_download_is_source_bound_and_verify_cannot_execute(self):
        self.pack()
        with patch.object(receive.subprocess, 'run') as run:
            result = receive.receive(self.outer, self.commit, verify_only=True)
        self.assertEqual(result, {'verified': True, 'format': 2, 'commit': self.commit})
        run.assert_not_called()
        with self.assertRaises(artifact.ArtifactError):
            receive.receive(self.outer, 'b' * 40, verify_only=True)

    def test_first_production_publish_is_blocked_without_completed_cutover(self):
        self.pack()
        with patch.object(receive.subprocess, 'run') as run, self.assertRaises(artifact.ArtifactError):
            receive.receive(self.outer, self.commit, root=self.root / 'not-migrated')
        run.assert_not_called()

    def test_flow_validation_entry_verifies_a_real_archive_without_reaching_deployment(self):
        self.pack()
        values={'archive':str(self.outer),'commit':self.commit,'pipeline':'fixture','build_number':'1'}
        with patch.object(verify_flow,'context',return_value=values), patch.object(receive.subprocess,'run') as run:
            result=verify_flow.run({})
        self.assertTrue(result['verified'])
        self.assertEqual(result['commit'],self.commit)
        run.assert_not_called()

    def test_traversal_extra_files_and_links_cannot_reach_execution(self):
        for name in ('../escape', '/tmp/escape', 'artifacts/extra.sh', 'artifacts/../escape'):
            member = tarfile.TarInfo(name); member.size = 1
            self.pack(member)
            with self.subTest(name=name), self.assertRaises(artifact.ArtifactError):
                receive.receive(self.outer, self.commit, verify_only=True)
        member = tarfile.TarInfo('artifacts/linked'); member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'
        self.pack(member)
        with self.assertRaises(artifact.ArtifactError):
            receive.receive(self.outer, self.commit, verify_only=True)


if __name__ == '__main__':
    unittest.main()
