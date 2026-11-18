import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import stage_native_artifact as subject


class NativeArtifactTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name)
        self.package=self.root/'artifacts';self.package.mkdir()
        self.incoming=self.root/'incoming'
        self.commit='a'*40
        self.name='blog-'+self.commit+'.tar.gz'
        self.content=b'fixture artifact bytes'
        self.digest=hashlib.sha256(self.content).hexdigest()
        (self.package/self.name).write_bytes(self.content)
        (self.package/(self.name+'.sha256')).write_text(self.digest+'  '+self.name+'\n',encoding='utf-8')
        (self.package/'release-native.sh').write_text('# fixture: never executed by this test\n')
        self.manifest={'commit':self.commit,'archive':self.name,'sha256':self.digest}
        self.write_manifest(self.manifest)

    def write_manifest(self,data):
        (self.package/'manifest.json').write_text(json.dumps(data),encoding='utf-8')

    def test_valid_artifact_stages_matching_files_and_passes_commit(self):
        with patch.object(subject.subprocess,'run') as release:
            self.assertEqual(subject.deploy(self.package,self.incoming,expected_commit=self.commit),self.commit)
        self.assertEqual((self.incoming/self.name).read_bytes(),self.content)
        self.assertEqual((self.incoming/(self.name+'.sha256')).read_text(),self.digest+'  '+self.name+'\n')
        self.assertEqual(sorted(path.name for path in self.incoming.iterdir()),[self.name,self.name+'.sha256'])
        if os.name=='posix':
            for path in self.incoming.iterdir(): self.assertEqual(path.stat().st_mode & 0o777,0o600)
        release.assert_called_once()
        self.assertEqual(release.call_args.args[0],['bash',str((self.package/'release-native.sh').resolve())])
        self.assertEqual(release.call_args.kwargs['env']['COMMIT_SHA'],self.commit)

    def test_tampered_archive_or_checksum_stops_before_any_staging(self):
        cases=((self.name,b'tampered'),(self.name+'.sha256',b'0'*64+b'  other-file\n'))
        for filename,bad in cases:
            path=self.package/filename;original=path.read_bytes();path.write_bytes(bad)
            with self.subTest(filename=filename),patch.object(subject.subprocess,'run') as release:
                with self.assertRaises(ValueError): subject.deploy(self.package,self.incoming)
                self.assertFalse(self.incoming.exists());release.assert_not_called()
            path.write_bytes(original)

    def test_unexpected_commit_or_archive_path_stops_before_deployment(self):
        cases=({'commit':'short'},{'archive':'../../outside.tar.gz'},{'sha256':'bad'},{'commit':'b'*40})
        for changes in cases:
            self.write_manifest({**self.manifest,**changes})
            with self.subTest(changes=changes),patch.object(subject.subprocess,'run') as release:
                with self.assertRaises(ValueError): subject.deploy(self.package,self.incoming,expected_commit=self.commit)
                self.assertFalse(self.incoming.exists());release.assert_not_called()

    def test_missing_release_script_stops_before_staging(self):
        (self.package/'release-native.sh').unlink()
        with patch.object(subject.subprocess,'run') as release:
            with self.assertRaises(ValueError): subject.deploy(self.package,self.incoming)
            self.assertFalse(self.incoming.exists());release.assert_not_called()


if __name__=='__main__': unittest.main()
