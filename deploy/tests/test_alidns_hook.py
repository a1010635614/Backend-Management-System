import io
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alidns_hook as hook

TOKEN = 'a' * 43


def answer(value=TOKEN, owner='_acme-challenge.kongqi.xyz.', flags='qr aa', kind='TXT'):
    return (';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n'
            ';; flags: ' + flags + '; QUERY: 1, ANSWER: 1\n' + owner + ' 600 IN ' + kind + ' "' + value + '"\n')


class TransportAndDnsTests(unittest.TestCase):
    def test_credentials_use_verified_https_body_and_fresh_nonces(self):
        client = hook.AliDNS('test-access-key-id', 'test-access-key-secret')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"RecordId":"100"}'
        client.opener.open = Mock(return_value=response)
        client.call('DescribeDomainRecordInfo', RecordId='100')
        first = client.opener.open.call_args.args[0]
        client.call('DescribeDomainRecordInfo', RecordId='100')
        second = client.opener.open.call_args.args[0]
        self.assertEqual(first.full_url, 'https://alidns.aliyuncs.com/')
        self.assertEqual(first.get_method(), 'POST')
        self.assertNotIn(b'test-access-key-secret', first.data)
        self.assertNotEqual(parse_qs(first.data.decode())['SignatureNonce'], parse_qs(second.data.decode())['SignatureNonce'])
        context = next(item._context for item in client.opener.handlers if hasattr(item, '_context'))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        with self.assertRaises(hook.HookError):
            hook.NoRedirect().redirect_request()

    def test_transport_and_api_error_bodies_cannot_leak_credentials(self):
        client = hook.AliDNS('test-access-key-id', 'test-access-key-secret')
        client.opener.open = Mock(side_effect=URLError('test-access-key-secret https://signed.example/?Signature=private'))
        with self.assertRaises(hook.HookError) as caught:
            client.call('DescribeDomainRecordInfo', RecordId='100')
        self.assertNotIn('test-access-key-secret', str(caught.exception))
        self.assertNotIn('Signature=', str(caught.exception))
        error = HTTPError(hook.ENDPOINT, 403, 'forbidden', {}, io.BytesIO(b'{"Code":"InvalidAccessKeyId.NotFound","Message":"test-access-key-secret"}'))
        client.opener.open = Mock(side_effect=error)
        with self.assertRaises(hook.ApiError) as caught:
            client.call('DescribeDomainRecordInfo', RecordId='100')
        self.assertEqual(str(caught.exception), 'AliDNS API rejected the request: InvalidAccessKeyId.NotFound')

    def test_unexpected_actions_and_malformed_api_errors_fail_closed(self):
        client = hook.AliDNS('test-access-key-id', 'test-access-key-secret')
        client.opener.open = Mock(side_effect=AssertionError('must not send'))
        with self.assertRaises(hook.HookError):
            client.call('DeleteSubDomainRecords', SubDomain='_acme-challenge.kongqi.xyz')
        self.assertEqual(str(hook.ApiError('private-secret\nmore')), 'AliDNS API rejected the request: InvalidResponse')

    def test_identifier_and_legacy_domain_must_agree_and_never_accept_other_domains(self):
        self.assertEqual(hook.invocation({'CERTBOT_IDENTIFIER':'kongqi.xyz', 'CERTBOT_VALIDATION':TOKEN}), TOKEN)
        self.assertEqual(hook.invocation({'CERTBOT_DOMAIN':'kongqi.xyz', 'CERTBOT_VALIDATION':TOKEN}), TOKEN)
        for environment in (
            {'CERTBOT_IDENTIFIER':'kongqi.xyz','CERTBOT_DOMAIN':'other.example','CERTBOT_VALIDATION':TOKEN},
            {'CERTBOT_DOMAIN':'*.kongqi.xyz','CERTBOT_VALIDATION':TOKEN},
            {'CERTBOT_DOMAIN':'cdn.kongqi.xyz','CERTBOT_VALIDATION':TOKEN},
            {'CERTBOT_DOMAIN':'kongqi.xyz','CERTBOT_VALIDATION':TOKEN+'\n'},
        ):
            with self.subTest(environment=environment), self.assertRaises(hook.HookError):
                hook.invocation(environment)

    def test_only_exact_authoritative_txt_answers_count_as_propagation(self):
        self.assertTrue(hook.authoritative_value(answer(), TOKEN))
        for output in (answer(flags='qr rd ra'), answer(owner='other.kongqi.xyz.'), answer(kind='CNAME'), answer(value='b'*43), answer().replace('NOERROR','SERVFAIL')):
            with self.subTest(output=output): self.assertFalse(hook.authoritative_value(output,TOKEN))

    def test_all_authorities_must_publish_the_value_before_the_deadline(self):
        clock = [0]
        def sleep(seconds): clock[0] += seconds
        def lookup(server,*args): return answer() if server=='@ns1.example.net' else answer(value='b'*43)
        with patch.object(hook,'nameservers',return_value=['ns1.example.net','ns2.example.net']), patch.object(hook,'dig',side_effect=lookup), patch.object(hook.time,'monotonic',side_effect=lambda:clock[0]), patch.object(hook.time,'sleep',side_effect=sleep):
            with self.assertRaises(hook.HookError): hook.wait_for_dns(TOKEN,10)
        self.assertGreaterEqual(clock[0],10)

    def test_record_listing_is_paginated_and_filters_fuzzy_matches(self):
        client = hook.AliDNS('test-access-key-id','test-access-key-secret')
        client.call = Mock(side_effect=[
            {'TotalCount':101,'DomainRecords':{'Record':[{'RR':'unrelated','Type':'TXT','Value':'keep'}]}},
            {'TotalCount':101,'DomainRecords':{'Record':[{'RR':hook.RR,'Type':'TXT','Value':TOKEN}]}},
        ])
        self.assertEqual(client.challenge_records(),[{'RR':hook.RR,'Type':'TXT','Value':TOKEN}])
        self.assertEqual(client.call.call_args.kwargs['PageNumber'],2)


class FakeApi:
    def __init__(self):
        self.records = {'10':{'RecordId':'10','DomainName':hook.ZONE,'RR':hook.RR,'Type':'TXT','Value':'z'*43,'Line':'default'}}
        self.adds = self.deletes = 0
        self.uncertain_add = self.uncertain_delete = self.reject_delete = False

    def challenge_records(self): return list(self.records.values())

    def call(self,action,**parameters):
        if action=='AddDomainRecord':
            self.adds += 1
            record_id = str(100+self.adds)
            self.records[record_id] = {'RecordId':record_id,**parameters}
            if self.uncertain_add: raise hook.HookError('simulated lost creation response')
            return {'RecordId':record_id}
        record_id = parameters['RecordId']
        if action=='DescribeDomainRecordInfo':
            if record_id not in self.records: raise hook.ApiError('InvalidRecordId.NotFound')
            return self.records[record_id].copy()
        if action=='DeleteDomainRecord':
            if self.reject_delete: raise hook.ApiError('Forbidden')
            self.deletes += 1
            del self.records[record_id]
            if self.uncertain_delete: raise hook.HookError('simulated lost deletion response')
            return {'RecordId':record_id}
        raise AssertionError('unexpected action')


@unittest.skipUnless(os.name=='posix','POSIX ownership and flock require Linux')
class OwnershipAndRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.journal = hook.Journal(self.base/'state')
        self.api = FakeApi()

    def auth(self,token=TOKEN,waiter=lambda *args:None):
        hook.authenticate(self.api,self.journal,token,waiter)

    def test_cleanup_removes_only_its_exact_record_and_is_idempotent(self):
        self.auth()
        value=self.journal.read(TOKEN)
        self.assertEqual(value['phase'],'visible')
        self.assertEqual(self.journal.path(TOKEN).stat().st_mode&0o777,0o600)
        hook.cleanup(self.api,self.journal,TOKEN)
        hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual(set(self.api.records),{'10'})
        self.assertEqual(self.api.deletes,1)
        self.assertEqual(self.journal.read(TOKEN)['phase'],'cleaned')

    def test_parallel_challenges_preserve_each_others_txt(self):
        self.auth(); self.auth('b'*43)
        hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual({item['Value'] for item in self.api.records.values()},{'z'*43,'b'*43})

    def test_existing_unowned_identical_txt_is_never_adopted_or_deleted(self):
        self.api.records['10']['Value']=TOKEN
        with self.assertRaises(hook.HookError): self.auth()
        self.assertIsNone(self.journal.read(TOKEN))
        self.assertEqual(self.api.adds,0)
        self.assertEqual(self.api.deletes,0)

    def test_lost_add_response_keeps_uncertain_state_without_duplicate_write(self):
        self.api.uncertain_add=True
        with self.assertRaises(hook.HookError): self.auth()
        with self.assertRaises(hook.HookError): self.auth()
        with self.assertRaises(hook.HookError): hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual(self.api.adds,1)
        self.assertEqual(self.api.deletes,0)
        self.assertEqual(self.journal.read(TOKEN)['phase'],'creating')

    def test_record_identity_change_prevents_cleanup_for_every_bound_field(self):
        self.auth()
        record_id=self.journal.read(TOKEN)['record_id']
        original=self.api.records[record_id].copy()
        for field in ('RecordId','DomainName','RR','Type','Value','Line'):
            with self.subTest(field=field):
                self.api.records[record_id]={**original,field:'changed'}
                with self.assertRaises(hook.HookError): hook.cleanup(self.api,self.journal,TOKEN)
                self.assertEqual(self.api.deletes,0)

    def test_propagation_failure_cleans_only_its_created_record(self):
        def fail(*args): raise hook.HookError('propagation timeout')
        with self.assertRaisesRegex(hook.HookError,'propagation timeout'): self.auth(waiter=fail)
        self.assertEqual(set(self.api.records),{'10'})
        self.assertEqual(self.journal.read(TOKEN)['phase'],'cleaned')

    def test_cleanup_failure_preserves_state_for_operator_recovery(self):
        self.api.reject_delete=True
        def fail(*args): raise hook.HookError('propagation timeout')
        with self.assertRaisesRegex(hook.HookError,'operator inspection'): self.auth(waiter=fail)
        self.assertIn('101',self.api.records)
        self.assertEqual(self.journal.read(TOKEN)['phase'],'deleting')
        self.api.reject_delete=False
        hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual(self.journal.read(TOKEN)['phase'],'cleaned')

    def test_lost_delete_response_can_be_reconciled_with_explicit_not_found(self):
        self.auth(); self.api.uncertain_delete=True
        with self.assertRaises(hook.HookError): hook.cleanup(self.api,self.journal,TOKEN)
        hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual(self.api.deletes,1)
        self.assertEqual(self.journal.read(TOKEN)['phase'],'cleaned')

    def test_bad_credentials_fail_before_any_creation_journal_or_dns_write(self):
        self.api.challenge_records=Mock(side_effect=hook.ApiError('InvalidAccessKeyId.NotFound'))
        with self.assertRaises(hook.ApiError): self.auth()
        self.assertIsNone(self.journal.read(TOKEN))
        self.assertEqual(self.api.adds,0)

    def test_unsafe_state_and_symlink_are_rejected_before_a_dns_action(self):
        self.auth()
        path=self.journal.path(TOKEN)
        path.chmod(0o644)
        with self.assertRaises(hook.HookError): hook.cleanup(self.api,self.journal,TOKEN)
        path.chmod(0o600)
        saved=self.base/'saved.json'; path.rename(saved); path.symlink_to(saved)
        with self.assertRaises(hook.HookError): hook.cleanup(self.api,self.journal,TOKEN)
        self.assertEqual(self.api.deletes,0)

    def test_concurrent_hook_lock_fails_without_performing_dns_actions(self):
        with self.journal.lock():
            with self.assertRaises(hook.HookError):
                with hook.Journal(self.journal.directory).lock(): self.fail('lock was acquired twice')

    def test_invalid_timeout_is_rejected_before_creating_a_record(self):
        with self.assertRaises(hook.HookError): hook.authenticate(self.api,self.journal,TOKEN,seconds=1)
        self.assertEqual(self.api.adds,0)
        self.assertIsNone(self.journal.read(TOKEN))


if __name__=='__main__': unittest.main()
