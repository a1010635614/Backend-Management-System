import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notify_feishu as notify

WEBHOOK = 'https://open.feishu.cn/open-apis/bot/v2/hook/00000000-0000-0000-0000-000000000000'
SECRET = 'test-signing-secret'


class NotificationTests(unittest.TestCase):
    def test_public_metadata_and_independent_provider_signature_vector(self):
        data = notify.payload('success', environ={'BUILD_NUMBER': '13', 'COMMIT_SHA': 'abc1234', 'FEISHU_SIGNING_SECRET': SECRET}, timestamp=1700000000)
        self.assertIn('BUILD_NUMBER: 13', data['content']['text'])
        self.assertEqual(data['sign'], '8+AD5scD8fIa8VJ+zWT5Bsd8iQwKT/D2d1mzhKogGP8=')
        self.assertNotIn(SECRET, json.dumps(data))

    def test_preview_cannot_send_and_does_not_show_credentials(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'FEISHU_WEBHOOK': WEBHOOK, 'FEISHU_SIGNING_SECRET': SECRET}), patch.object(sys, 'argv', ['notify_feishu.py', 'failure', '--preview']), patch.object(notify, 'send_notification') as send, contextlib.redirect_stdout(output):
            notify.main()
        send.assert_not_called()
        self.assertNotIn(SECRET, output.getvalue()); self.assertNotIn(WEBHOOK, output.getvalue())

    def test_destination_is_exact_and_redirects_are_not_followed(self):
        for value in (WEBHOOK.replace('https:', 'http:'), WEBHOOK + '?x=1', WEBHOOK.replace('open.feishu.cn', 'open.feishu.cn.evil.example')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                notify.validate_webhook(value)
        handler = notify.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_vendor_rejection_is_not_reported_as_success_or_echoed(self):
        response = io.BytesIO(json.dumps({'code': 19024, 'msg': SECRET}).encode()); response.status = 200
        with patch.object(notify.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            with self.assertRaises(notify.NotificationError) as error:
                notify.send_notification(WEBHOOK, {'msg_type': 'text'})
        self.assertNotIn(SECRET, str(error.exception))


if __name__ == '__main__':
    unittest.main()
