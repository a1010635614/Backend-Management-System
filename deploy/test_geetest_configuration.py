import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dotenv import dotenv_values
from configure_mail_remote import serialize_environment
import configure_geetest_remote as setup


class GeeTestConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.envpath=Path(self.work.name)/'environment'
        self.original=b'DATABASE_URL=postgresql://unchanged\nJWT_SECRET=keep-jwt\nMAIL_PASSWORD="keep-$mail"\nCOS_SECRET_KEY=keep-cos\nGEETEST_ID=old-scene\nGEETEST_KEY=old-key\n'
        self.envpath.write_bytes(self.original)
        self.credentials={'captcha_id':'a'*32,'captcha_key':'b'*32}
        self.output=io.StringIO()
        self.use_patch(contextlib.redirect_stdout(self.output))
        self.use_patch(patch.object(setup,'serialize_environment',serialize_environment,create=True))
        self.use_patch(patch.object(setup,'replace_file',side_effect=lambda path,data,owner:path.write_bytes(data),create=True))
        self.restart=self.use_patch(patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess(['systemctl'],0)))

    def use_patch(self,manager):
        value=manager.__enter__()
        self.addCleanup(manager.__exit__,None,None,None)
        return value

    def test_only_geetest_fields_change_and_key_is_not_logged(self):
        with patch.object(setup,'application_ready',return_value=True):
            setup.install_credentials(self.credentials,self.envpath)
        actual=dotenv_values(self.envpath,interpolate=False)
        before=dotenv_values(stream=io.StringIO(self.original.decode()),interpolate=False)
        self.assertEqual(actual,{**before,'GEETEST_ID':'a'*32,'GEETEST_KEY':'b'*32})
        self.assertIn('has NOT been validated',self.output.getvalue())
        self.assertNotIn(self.credentials['captcha_key'],self.output.getvalue())

    def test_failed_health_restores_exact_environment_and_restarts(self):
        with patch.object(setup,'application_ready',return_value=False),self.assertRaises(SystemExit):
            setup.install_credentials(self.credentials,self.envpath)
        self.assertEqual(self.envpath.read_bytes(),self.original)
        self.assertEqual(self.restart.call_count,2)
        self.assertNotIn(self.credentials['captcha_key'],self.output.getvalue())

    def test_failed_restart_restores_environment(self):
        self.restart.side_effect=[subprocess.CalledProcessError(1,['systemctl']),subprocess.CompletedProcess(['systemctl'],0)]
        with self.assertRaises(SystemExit): setup.install_credentials(self.credentials,self.envpath)
        self.assertEqual(self.envpath.read_bytes(),self.original)
        self.assertIn('previous environment restored',self.output.getvalue())

    def test_partial_credentials_are_rejected_before_mutation(self):
        for values in ({'captcha_id':'a'*32},{**self.credentials,'captcha_key':'b'*31+'\n'},{**self.credentials,'captcha_id':'短'*32}):
            with self.subTest(values=values),self.assertRaises(ValueError):
                setup.install_credentials(values,self.envpath)
        self.assertEqual(self.envpath.read_bytes(),self.original)
        self.restart.assert_not_called()

    def test_ready_requires_database_health_and_the_installed_public_id(self):
        import httpx
        with patch.object(setup.time,'sleep'),patch.object(setup.httpx,'get') as get:
            get.side_effect=lambda url,**kwargs:httpx.Response(200,json={'status':'UP'} if url.endswith('/health') else {'captchaId':'old-scene'})
            self.assertFalse(setup.application_ready('a'*32))
            get.side_effect=lambda url,**kwargs:httpx.Response(200,json={'status':'UP'} if url.endswith('/health') else {'captchaId':'a'*32})
            self.assertTrue(setup.application_ready('a'*32))
            get.side_effect=lambda url,**kwargs:httpx.Response(503,json={'status':'DOWN'}) if url.endswith('/health') else httpx.Response(200,json={'captchaId':'a'*32})
            self.assertFalse(setup.application_ready('a'*32))


if __name__=='__main__': unittest.main()
