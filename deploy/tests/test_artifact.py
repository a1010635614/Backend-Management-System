import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import artifact


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.commit = 'a' * 40
        for name in artifact.ROOTS:
            (self.root / name).mkdir(parents=True)
        for name in (*artifact.FILES, *artifact.REQUIRED):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n', encoding='utf-8')

    def test_deterministic_package_can_be_verified_and_extracted(self):
        directory = artifact.package(self.root, self.commit)
        first = (directory / ('blog-' + self.commit + '.tar.gz')).read_bytes()
        artifact.package(self.root, self.commit)
        self.assertEqual(first, (directory / ('blog-' + self.commit + '.tar.gz')).read_bytes())
        destination = self.root / 'stage'
        artifact.extract(directory, self.commit, destination)
        self.assertEqual((destination / 'backend/app/main.py').read_text(), '# fixture\n')

    def test_commit_and_manifest_must_match_expected_source(self):
        directory = artifact.package(self.root, self.commit)
        with self.assertRaises(artifact.ArtifactError):
            artifact.verify(directory, 'b' * 40)
        for value in ('main', 'a' * 7, '../escape', 'a' * 40 + '\n'):
            with self.subTest(value=value), self.assertRaises(artifact.ArtifactError):
                artifact.package(self.root, value)

    def test_changed_payload_is_rejected_before_extracting(self):
        directory = artifact.package(self.root, self.commit)
        archive = directory / ('blog-' + self.commit + '.tar.gz')
        archive.write_bytes(archive.read_bytes() + b'changed')
        destination = self.root / 'stage'
        with self.assertRaises(artifact.ArtifactError):
            artifact.extract(directory, self.commit, destination)
        self.assertFalse(destination.exists())

    def test_environment_and_private_key_files_cannot_be_packaged(self):
        for name in ('backend/app/.env', 'backend/app/credential.pem', 'backend/app/private.key', 'backend/app/data.sqlite'):
            path = self.root / name
            path.write_text('fixture')
            with self.subTest(name=name), self.assertRaises(artifact.ArtifactError):
                artifact.package(self.root, self.commit)
            path.unlink()

    def altered(self, member, content=b'fixture'):
        directory = artifact.package(self.root, self.commit)
        archive = directory / ('blog-' + self.commit + '.tar.gz')
        with tarfile.open(archive) as tar:
            original = [(entry, tar.extractfile(entry).read()) for entry in tar]
        with tarfile.open(archive, 'w:gz') as tar:
            for entry, data in original:
                tar.addfile(entry, io.BytesIO(data))
            tar.addfile(member, io.BytesIO(content) if member.isfile() else None)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['sha256'] = digest
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        (directory / (archive.name + '.sha256')).write_text(digest + '  ' + archive.name + '\n')
        return directory

    def test_self_consistent_archives_still_reject_traversal_and_unexpected_members(self):
        for name in ('../escape', '/tmp/escape', 'backend/app/../escape', 'backend\\app\\escape.py', 'etc/passwd', 'backend/app/.env'):
            member = tarfile.TarInfo(name); member.size = 7
            directory = self.altered(member)
            with self.subTest(name=name), self.assertRaises(artifact.ArtifactError):
                artifact.verify(directory, self.commit)

    def test_links_devices_and_duplicate_members_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            member = tarfile.TarInfo('backend/app/linked')
            member.type = kind; member.linkname = '/etc/passwd'
            directory = self.altered(member)
            with self.subTest(kind=kind), self.assertRaises(artifact.ArtifactError):
                artifact.verify(directory, self.commit)
        member = tarfile.TarInfo('backend/app/main.py'); member.size = 7
        directory = self.altered(member)
        with self.assertRaises(artifact.ArtifactError):
            artifact.verify(directory, self.commit)

    def test_missing_application_and_checksum_file_are_rejected(self):
        (self.root / 'frontend-admin/dist/index.html').unlink()
        with self.assertRaises(artifact.ArtifactError):
            artifact.package(self.root, self.commit)
        (self.root / 'frontend-admin/dist/index.html').write_text('fixture')
        directory = artifact.package(self.root, self.commit)
        (directory / ('blog-' + self.commit + '.tar.gz.sha256')).write_text('invalid')
        with self.assertRaises(artifact.ArtifactError):
            artifact.verify(directory, self.commit)


if __name__ == '__main__':
    unittest.main()
