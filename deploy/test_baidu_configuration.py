import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dotenv import dotenv_values
from configure_mail_remote import serialize_environment
import configure_baidu_remote as setup


class BaiduConfigurationTests(unittest.TestCase):
    def test_public_id_update_preserves_credentials_and_failed_health_restores(self):
        with tempfile.TemporaryDirectory() as work:
            envpath=Path(work)/'environment'
            original=b'JWT_SECRET=keep-jwt\nMAIL_PASSWORD="keep-$mail"\nCOS_SECRET_KEY=keep-cos\nGEETEST_KEY=keep-gt4\n'
            for healthy in (True,False):
                envpath.write_bytes(original)
                output=io.StringIO()
                with self.subTest(healthy=healthy),contextlib.redirect_stdout(output),patch.object(setup,'serialize_environment',serialize_environment,create=True),patch.object(setup,'replace_file',side_effect=lambda path,data,owner:path.write_bytes(data),create=True),patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess(['systemctl'],0)) as restart,patch.object(setup,'application_ready',return_value=healthy):
                    if healthy:
                        setup.install_tracking_id('a'*32,envpath)
                        expected={**dotenv_values(stream=io.StringIO(original.decode()),interpolate=False),'BAIDU_HM_ID':'a'*32}
                        self.assertEqual(dotenv_values(envpath,interpolate=False),expected)
                        self.assertEqual(restart.call_count,1)
                    else:
                        with self.assertRaises(SystemExit): setup.install_tracking_id('a'*32,envpath)
                        self.assertEqual(envpath.read_bytes(),original)
                        self.assertEqual(restart.call_count,2)
                    self.assertNotIn('keep-',output.getvalue())

    def test_numeric_site_id_and_scripts_are_rejected_before_server_access(self):
        with patch.object(setup.subprocess,'run') as restart:
            for value in ('12345678','<script src="https://hm.baidu.com/hm.js?'+'a'*32+'"></script>',None,'a'*31+'\n'):
                with self.subTest(value=value),self.assertRaises(ValueError): setup.install_tracking_id(value,Path('does-not-exist'))
            restart.assert_not_called()


if __name__=='__main__': unittest.main()
