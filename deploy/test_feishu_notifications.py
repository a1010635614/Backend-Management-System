import contextlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
import configure_feishu as setup
import notify

WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/00000000-0000-0000-0000-000000000000'
SECRET='test-signing-secret'


class FeishuNotificationTests(unittest.TestCase):
    def test_preview_and_cancel_cannot_send(self):
        values={'group':'Deployment test group','webhook':WEBHOOK,'secret':SECRET}
        output=io.StringIO()
        with contextlib.redirect_stdout(output),patch.object(setup,'credentials',return_value=values),patch.object(setup,'confirm_send',return_value=False) as confirm,patch.object(setup,'send_notification') as send:
            setup.main()
            confirm.assert_called_once()
            self.assertIn('机器人接入验证',confirm.call_args.args[1])
            send.assert_not_called()
        with contextlib.redirect_stdout(output),patch.object(setup,'credentials',return_value=None),patch.object(setup,'confirm_send') as confirm,patch.object(setup,'send_notification') as send:
            setup.main()
            confirm.assert_not_called();send.assert_not_called()
        self.assertNotIn(SECRET,output.getvalue());self.assertNotIn(WEBHOOK,output.getvalue())

    def test_confirmed_message_matches_preview_and_is_sent_once(self):
        values={'group':'Deployment test group','webhook':WEBHOOK,'secret':SECRET}
        output=io.StringIO()
        with contextlib.redirect_stdout(output),patch.object(setup,'credentials',return_value=values),patch.object(setup,'confirm_send',return_value=True) as confirm,patch.object(setup,'send_notification') as send:
            setup.main()
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0],WEBHOOK)
        sent=send.call_args.args[1]
        self.assertEqual(sent['content']['text'],confirm.call_args.args[1])
        self.assertIn('sign',sent);self.assertIn('timestamp',sent)
        self.assertNotIn(SECRET,output.getvalue());self.assertNotIn(WEBHOOK,output.getvalue())

    def test_cli_preview_never_posts_or_prints_credentials(self):
        output=io.StringIO()
        with patch.dict(os.environ,{'FEISHU_WEBHOOK':WEBHOOK,'FEISHU_SIGNING_SECRET':SECRET,'COMMIT_SHA':'abc1234'}),patch.object(sys,'argv',['notify.py','success','--preview']),contextlib.redirect_stdout(output),patch.object(notify,'send_notification') as send:
            notify.main()
        self.assertIn('abc1234',output.getvalue());send.assert_not_called()
        self.assertNotIn(SECRET,output.getvalue());self.assertNotIn(WEBHOOK,output.getvalue())

    def test_only_exact_https_webhook_endpoint_is_accepted(self):
        invalid=(WEBHOOK.replace('https:','http:'),WEBHOOK.replace('open.feishu.cn','open.feishu.cn.evil.example'),WEBHOOK+'?extra=value',WEBHOOK+'#fragment',WEBHOOK.replace('open.feishu.cn','username@open.feishu.cn'),WEBHOOK+'\n')
        with patch.object(notify.urllib.request,'build_opener') as opener:
            for webhook in invalid:
                with self.subTest(webhook=webhook),self.assertRaises(ValueError):
                    notify.send_notification(webhook,{'msg_type':'text'})
            opener.assert_not_called()

    def test_delivery_checks_http_and_feishu_result_without_error_details(self):
        cases=((200,{'code':0},True),(200,{'StatusCode':0},True),(500,{'code':0},False),(200,{'code':19024,'msg':SECRET},False),(200,[],False),(200,{'code':False},False))
        for status,result,accepted in cases:
            response=io.BytesIO(json.dumps(result).encode());response.status=status
            with self.subTest(status=status,result=result),patch.object(notify.urllib.request,'build_opener') as build:
                build.return_value.open.return_value=response
                if accepted:
                    notify.send_notification(WEBHOOK,{'msg_type':'text','content':{'text':'test'}})
                else:
                    with self.assertRaises(notify.NotificationError) as error:
                        notify.send_notification(WEBHOOK,{'msg_type':'text','content':{'text':'test'}})
                    self.assertNotIn(SECRET,str(error.exception));self.assertNotIn(WEBHOOK,str(error.exception))
                build.assert_called_once_with(notify.NoRedirect)
                request=build.return_value.open.call_args.args[0]
                self.assertEqual(request.get_method(),'POST')
                self.assertEqual(build.return_value.open.call_args.kwargs['timeout'],15)

    def test_deployment_metadata_and_signature(self):
        data=notify.payload('failure',environ={'DEPLOY_ENV':'production','COMMIT_SHA':'abc1234','BRANCH_NAME':'main','SITE_URL':'https://kongqi.xyz','PIPELINE_URL':'https://flow.example/runs/42','FEISHU_SIGNING_SECRET':SECRET},timestamp=1700000000)
        text=data['content']['text']
        for expected in ('failure','production','abc1234','main','https://kongqi.xyz','https://flow.example/runs/42'):
            self.assertIn(expected,text)
        self.assertEqual(data['timestamp'],'1700000000')
        self.assertNotIn(SECRET,json.dumps(data))
        self.assertEqual(data['sign'],'8+AD5scD8fIa8VJ+zWT5Bsd8iQwKT/D2d1mzhKogGP8=')

    def test_missing_signature_configuration_stops_before_posting(self):
        with patch.dict(os.environ,{'FEISHU_WEBHOOK':WEBHOOK,'FEISHU_SIGNING_SECRET':''}),patch.object(sys,'argv',['notify.py','failure']),patch.object(notify,'send_notification') as send:
            with self.assertRaises(ValueError): notify.main()
            send.assert_not_called()


if __name__=='__main__': unittest.main()
