"""Checks for the real configuration gate and restoration path; no external I/O."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.cdn import signed_cdn_url
from configure_mail_remote import serialize_environment
import configure_cdn_remote as setup


class CdnConfigurationTests(unittest.TestCase):
    def test_real_signatures_and_warm_cache_auth_gate(self):
        data = b'private test picture'
        key = 'ExampleKey123'
        asset = {'id': 'test', 'key': 'uploads/1/file.png', 'size': len(data), 'content_type': 'image/png'}
        calls = []

        def respond(request):
            query = parse_qs(request.url.query.decode())
            calls.append(str(request.url))
            if request.url.host == 'origin.example.com':
                return httpx.Response(200, content=data,headers={'content-type':'image/png'}) if query else httpx.Response(403)
            if not query:
                return httpx.Response(403)
            issued = int(query['t'][0])
            expected = signed_cdn_url('https://cdn.kongqi.xyz', asset['key'], key, timestamp=issued)
            valid = str(request.url) == expected and issued >= 1700000000 - 300
            return httpx.Response(200, content=data, headers={'x-cache-lookup': 'Cache Hit','content-type':'image/png'}) if valid else httpx.Response(403)

        class Origin:
            def get_presigned_url(self, **kwargs):
                return 'https://origin.example.com/uploads/1/file.png?q-signature=test'

        with httpx.Client(transport=httpx.MockTransport(respond)) as web,patch('app.cdn.time.time', return_value=1700000000):
            reports = setup.verify_delivery(web, Origin(), 'bucket', 'https://cdn.kongqi.xyz', key, [asset], signed_cdn_url)
        self.assertTrue(reports[0]['content_matches'])
        self.assertTrue(reports[0]['unsigned_invalid_expired_denied'])
        self.assertEqual(reports[0]['cache_headers'], {'x-cache-lookup': 'Cache Hit'})
        self.assertEqual(len(calls), 7)

    def test_unsafe_delivery_never_passes_preflight(self):
        asset = {'id': 'test', 'key': 'uploads/1/file.png', 'size': 3, 'content_type': 'image/png'}

        class Origin:
            def get_presigned_url(self, **kwargs):
                return 'https://origin.example.com/uploads/1/file.png?q-signature=test'

        for failure in ('public-origin', 'wrong-bytes', 'wrong-size', 'wrong-type', 'unsigned-warm', 'invalid-sign', 'expired-sign'):
            def respond(request):
                query = parse_qs(request.url.query.decode())
                if request.url.host == 'origin.example.com':
                    return httpx.Response(200, content=b'abc',headers={'content-type':'image/png'}) if query or failure == 'public-origin' else httpx.Response(403)
                if not query:
                    return httpx.Response(200, content=b'abc') if failure == 'unsigned-warm' else httpx.Response(403)
                issued = int(query['t'][0])
                expected = signed_cdn_url('https://cdn.kongqi.xyz', asset['key'], 'ExampleKey123', timestamp=issued)
                if issued < 1700000000 - 300:
                    return httpx.Response(200, content=b'abc') if failure == 'expired-sign' else httpx.Response(403)
                if str(request.url) != expected:
                    return httpx.Response(200, content=b'abc') if failure == 'invalid-sign' else httpx.Response(403)
                data = b'bad' if failure == 'wrong-bytes' else b'oversized' if failure == 'wrong-size' else b'abc'
                return httpx.Response(200, content=data,headers={'content-type':'text/html' if failure == 'wrong-type' else 'image/png'})
            with self.subTest(failure=failure),httpx.Client(transport=httpx.MockTransport(respond)) as web,patch('app.cdn.time.time',return_value=1700000000),self.assertRaises(setup.CdnCheckFailed) as error:
                setup.verify_delivery(web, Origin(), 'bucket', 'https://cdn.kongqi.xyz', 'ExampleKey123', [asset], signed_cdn_url)
            self.assertNotIn('ExampleKey123', str(error.exception))

    def test_configuration_preserves_other_secrets_and_restores_on_failure(self):
        with tempfile.TemporaryDirectory() as work:
            envpath = Path(work) / 'environment'
            original = b'JWT_SECRET=keep-jwt\nMAIL_PASSWORD="keep-$mail"\nCOS_SECRET_KEY=keep-cos\nGEETEST_KEY=keep-gt4\n'
            for healthy in (True, False):
                envpath.write_bytes(original)
                with self.subTest(healthy=healthy),patch.object(setup,'serialize_environment',serialize_environment,create=True),patch.object(setup,'replace_file',side_effect=lambda path,data,owner:path.write_bytes(data),create=True),patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess(['systemctl'],0)) as restart,patch.object(setup,'application_ready',return_value=healthy):
                    if healthy:
                        setup.install_configuration('https://cdn.kongqi.xyz','ExampleKey123',{'id':'test'},signed_cdn_url,envpath)
                        expected = {**dotenv_values(stream=io.StringIO(original.decode()),interpolate=False), 'CDN_BASE_URL':'https://cdn.kongqi.xyz','CDN_AUTH_KEY':'ExampleKey123'}
                        self.assertEqual(dotenv_values(envpath,interpolate=False),expected)
                        self.assertEqual(restart.call_count,1)
                    else:
                        with self.assertRaises(setup.CdnCheckFailed):
                            setup.install_configuration('https://cdn.kongqi.xyz','ExampleKey123',{'id':'test'},signed_cdn_url,envpath)
                        self.assertEqual(envpath.read_bytes(),original)
                        self.assertEqual(restart.call_count,2)

    def test_media_readiness_requires_correct_signature_and_cache_headers(self):
        asset = {'id':'test','key':'uploads/1/file.png'}
        for failure in ('none', 'wrong-key', 'cached-redirect', 'old-timestamp', 'wrong-host'):
            def respond(request):
                if request.url.path == '/api/health':
                    return httpx.Response(200,json={'status':'UP'})
                target = signed_cdn_url('https://cdn.kongqi.xyz',asset['key'],
                                        'AnotherKey123' if failure == 'wrong-key' else 'ExampleKey123',
                                        timestamp=1600000000 if failure == 'old-timestamp' else 1700000000)
                if failure == 'wrong-host': target=target.replace('cdn.kongqi.xyz','wrong.example.com')
                return httpx.Response(307,headers={'Location':target,'Cache-Control':'public' if failure == 'cached-redirect' else 'private, no-store','Referrer-Policy':'no-referrer'})
            client_class = httpx.Client
            with self.subTest(failure=failure),patch.object(setup.httpx,'Client',side_effect=lambda **kwargs:client_class(transport=httpx.MockTransport(respond),**kwargs)),patch('app.cdn.time.time',return_value=1700000000),patch.object(setup.time,'sleep'):
                self.assertEqual(setup.application_ready('https://cdn.kongqi.xyz','ExampleKey123',asset,signed_cdn_url), failure == 'none')


if __name__ == '__main__': unittest.main()
