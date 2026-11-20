import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_runtime import COPY_KEYS, build_values, literal_environment, plan


class RuntimePreparationTests(unittest.TestCase):
    def fixture(self):
        values = {key: 'fixture-value' for key in COPY_KEYS}
        values.update(MAIL_PORT='465', BAIDU_HM_ID='a' * 32, CDN_BASE_URL='https://cdn.example.com',
                      ADMIN_EMAILS='admin@example.com', DATABASE_URL='old-database-connection',
                      JWT_SECRET='old-jwt-secret', FEISHU_WEBHOOK='not-for-this-runtime',
                      GITHUB_APP_KEY='not-for-this-runtime', TEST_ONLY_CANDIDATE='1')
        return values

    def test_plan_cannot_read_any_source_or_container(self):
        with patch.object(Path, 'open', side_effect=AssertionError('no reads')):
            result = plan()
        self.assertEqual(set(result['copy_keys']), set(COPY_KEYS))
        self.assertEqual(result['target'], 'new production only')

    def test_only_allowlisted_integrations_are_preserved_and_local_secrets_are_fresh(self):
        fixture = self.fixture()
        original = ''.join(key + '=' + json.dumps(value) + '\n' for key, value in fixture.items())
        result = build_values(original)
        for key in COPY_KEYS: self.assertEqual(result[key], fixture[key])
        self.assertTrue(result['DATABASE_URL'].startswith('postgresql+asyncpg://'))
        self.assertNotEqual(result['JWT_SECRET'], fixture['JWT_SECRET'])
        self.assertNotEqual(result['JWT_SECRET'], build_values(original)['JWT_SECRET'])
        for key in ('FEISHU_WEBHOOK', 'GITHUB_APP_KEY', 'TEST_ONLY_CANDIDATE'):
            self.assertNotIn(key, result)
        self.assertNotIn(fixture['DATABASE_URL'], literal_environment(result))

    def test_line_injection_and_invalid_keys_are_rejected_before_writing(self):
        for key, value in [('MAIL_PASSWORD', 'fixture\nADMIN_EMAILS=other@example.com'),
                           ('MAIL_PASSWORD', 'fixture\rdata'), ('BAD-KEY', 'fixture')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                literal_environment({key: value})

    def test_missing_setting_fails_without_showing_any_input(self):
        fixture = self.fixture(); del fixture['MAIL_PASSWORD']
        original = ''.join(key + '=' + json.dumps(value) + '\n' for key, value in fixture.items())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(ValueError) as caught:
            build_values(original)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('old-jwt-secret', str(caught.exception))


if __name__ == '__main__': unittest.main()
