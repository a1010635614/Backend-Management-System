import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import package_native
from stage_native_artifact import verify


class NativePackageTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name)
        self.commit='d'*40
        self.files=('backend/app/main.py','backend/migrations/versions/0001.py','backend/tests/test_api.py','backend/alembic.ini','backend/requirements.txt','frontend/dist/index.html','deploy/release-native.sh','deploy/stage_native_artifact.py')
        for name in self.files:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture\n')

    def test_package_round_trip_matches_staging_and_excludes_private_roots(self):
        for name in ('.env','.local/private-key.pem','backend/.env','backend/app/__pycache__/ignored.pyc'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private-fixture')
        output=package_native.create_package(self.root,self.commit)
        artifact=verify(output,self.commit)
        with tarfile.open(artifact.archive) as tar:
            names=set(tar.getnames())
            self.assertEqual(names,set(self.files)-{'deploy/release-native.sh','deploy/stage_native_artifact.py'})
            self.assertTrue(all(member.isfile() for member in tar.getmembers()))
        manifest=json.loads((output/'manifest.json').read_text())
        self.assertEqual(manifest['commit'],self.commit)
        for name in package_native.SCRIPTS: self.assertEqual((output/name).read_bytes(),(self.root/'deploy'/name).read_bytes())

    def test_invalid_commit_stops_before_creating_outputs(self):
        with self.assertRaises(ValueError): package_native.create_package(self.root,'short')
        self.assertFalse((self.root/'artifacts').exists())

    def test_missing_input_stops_before_creating_outputs(self):
        (self.root/'backend/requirements.txt').unlink()
        with self.assertRaises(ValueError): package_native.create_package(self.root,self.commit)
        self.assertFalse((self.root/'artifacts').exists())

    def test_nested_credentials_are_rejected_before_packaging(self):
        (self.root/'backend/app/.env').write_text('private-fixture')
        with self.assertRaises(ValueError): package_native.create_package(self.root,self.commit)
        self.assertFalse((self.root/'artifacts').exists())


if __name__=='__main__': unittest.main()
