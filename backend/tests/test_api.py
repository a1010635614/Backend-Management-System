"""本地接口回归；SQLite 验证业务行为，不替代 PostgreSQL 行锁/迁移验收。"""
import os
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.parse import urlparse,parse_qs
from datetime import datetime, timedelta, timezone
from hashlib import sha256

work = tempfile.TemporaryDirectory()
test_url=os.environ.get("TEST_DATABASE_URL")
if test_url:
    from sqlalchemy.engine import make_url
    if make_url(test_url).database!="blog_ci" or not make_url(test_url).drivername.startswith("postgresql"):
        raise RuntimeError("集成测试只允许专用 blog_ci 数据库")
os.environ["DATABASE_URL"] = test_url or "sqlite:///" + work.name + "/api.db"
os.environ["ADMIN_EMAILS"] = "admin@example.com"
from fastapi.testclient import TestClient
from app.main import app, Base, engine, SessionLocal, User, Code, settings

def tearDownModule():
    engine.dispose()
    work.cleanup()

class ApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.client = TestClient(app)

    def token(self, email):
        code = "123456"
        with SessionLocal() as db:
            db.add(Code(email=email, digest=sha256((email+code+settings.jwt_secret).encode()).hexdigest(), expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))
            db.commit()
        response=self.client.post("/api/auth/email/verify",json={"email":email,"code":code})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post("/api/auth/email/verify",json={"email":email,"code":code}).status_code,401)
        return {"Authorization":"Bearer "+response.json()["access_token"]}

    def test_admin_crud_and_permission(self):
        body={"title":"title","summary":"summary","content":"body","category":"notes"}
        self.assertEqual(self.client.post('/api/posts',json=body).status_code,401)
        reader=self.token('reader@example.com')
        self.assertEqual(self.client.post('/api/posts',json=body,headers=reader).status_code,403)
        admin=self.token('admin@example.com')
        created=self.client.post('/api/posts',json=body,headers=admin)
        self.assertEqual(created.status_code,201,created.text)
        pid=created.json()['id']
        self.assertEqual(self.client.get(f'/api/posts/{pid}').json()['content'],'body')
        self.assertEqual(self.client.put(f'/api/posts/{pid}',json={**body,'title':'changed'},headers=admin).status_code,200)
        self.assertEqual(self.client.delete(f'/api/posts/{pid}',headers=admin).status_code,204)
        self.assertEqual(self.client.get(f'/api/posts/{pid}').status_code,404)

    def test_code_attempt_limit(self):
        with SessionLocal() as db:
            db.add(Code(email='a@example.com',digest='invalid',expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)));db.commit()
        for _ in range(5): self.assertEqual(self.client.post('/api/auth/email/verify',json={'email':'a@example.com','code':'111111'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/email/verify',json={'email':'a@example.com','code':'111111'}).status_code,429)

    def test_cos_native_presign_and_swagger(self):
        admin=self.token('admin@example.com')
        with patch.multiple(settings,cos_secret_id='test-id',cos_secret_key='test-key',cos_region='ap-shanghai',cos_bucket='test-1250000000',cos_public_base_url='https://media.example.com'):
            result=self.client.post('/api/uploads/presign',params={'filename':'../../a.png','content_type':'image/png'},headers=admin)
        self.assertEqual(result.status_code,200,result.text)
        data=result.json();url=urlparse(data['uploadUrl']);query=parse_qs(url.query)
        self.assertEqual(url.scheme,'https')
        self.assertEqual(url.hostname,'test-1250000000.cos.ap-shanghai.myqcloud.com')
        self.assertIn('q-signature',query)
        self.assertIn('content-type',query['q-header-list'][0])
        self.assertNotIn('..',data['key'])
        self.assertTrue(data['publicUrl'].startswith('https://media.example.com/uploads/'))
        schema=self.client.get('/openapi.json').json()
        self.assertEqual(schema['components']['securitySchemes']['HTTPBearer']['scheme'],'bearer')

    def test_geetest_failure_blocks_smtp(self):
        with patch.multiple(settings,geetest_id='id',geetest_key='key',mail_host='smtp.example.com'),patch('app.main.httpx.post',return_value=Mock(json=lambda:{'result':'fail'})),patch('smtplib.SMTP') as smtp:
            result=self.client.post('/api/auth/email/send',json={'email':'admin@example.com','geetest':{'lot_number':'lot','captcha_output':'output','pass_token':'pass','gen_time':'1'}})
            self.assertEqual(result.status_code,401)
            smtp.assert_not_called()

    def test_mail_delivery_then_verify(self):
        import re
        with patch.multiple(settings,mail_host='smtp.example.com',geetest_id=''),patch('smtplib.SMTP') as smtp:
            result=self.client.post('/api/auth/email/send',json={'email':'mail@example.com'})
            self.assertEqual(result.status_code,202,result.text)
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            code=re.search(r'\b\d{6}\b',message.get_content()).group()
            self.assertEqual(self.client.post('/api/auth/email/send',json={'email':'mail@example.com'}).status_code,429)
            self.assertEqual(self.client.post('/api/auth/email/verify',json={'email':'mail@example.com','code':code}).status_code,200)

    def test_smtp_ssl_465_delivery(self):
        import re
        with patch.multiple(settings,mail_host='smtpdm.aliyun.com',mail_port=465,geetest_id='',mail_username='noreply@example.com',mail_password='test-only'),patch('smtplib.SMTP_SSL') as secure,patch('smtplib.SMTP') as plain:
            result=self.client.post('/api/auth/email/send',json={'email':'recipient@example.com'})
            self.assertEqual(result.status_code,202,result.text)
            plain.assert_not_called()
            context=secure.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            smtp=secure.return_value.__enter__.return_value
            smtp.starttls.assert_not_called()
            smtp.login.assert_called_once_with('noreply@example.com','test-only')
            code=re.search(r'\b\d{6}\b',smtp.send_message.call_args.args[0].get_content()).group()
            self.assertEqual(self.client.post('/api/auth/email/verify',json={'email':'recipient@example.com','code':code}).status_code,200)

    def test_smtp_failure_does_not_save_code(self):
        from sqlalchemy import select,func
        with patch.multiple(settings,mail_host='smtpdm.aliyun.com',mail_port=465,geetest_id=''),patch('smtplib.SMTP_SSL',side_effect=OSError('private transport details')):
            result=self.client.post('/api/auth/email/send',json={'email':'recipient@example.com'})
            self.assertEqual(result.status_code,502)
            self.assertNotIn('private transport details',result.text)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count(Code.id))),0)

    def test_pageviews_count_unique_visitors(self):
        for name,visitor in [('pageview','one'),('pageview','one'),('pageview','two'),('click','three')]:
            self.assertEqual(self.client.post('/api/analytics/events',json={'event':name,'path':'/','visitorId':visitor}).status_code,202)
        self.assertEqual(self.client.get('/api/analytics/summary',headers=self.token('admin@example.com')).json(),{'pv':3,'uv':2})

    @unittest.skipUnless(test_url,"需要专用 PostgreSQL 集成测试库")
    def test_postgres_concurrent_code_consumption(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        email='concurrent@example.com';code='123456'
        with SessionLocal() as db:
            db.add(Code(email=email,digest=sha256((email+code+settings.jwt_secret).encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)));db.commit()
        barrier=Barrier(2)
        def verify():
            with TestClient(app) as client:
                barrier.wait(timeout=10)
                return client.post('/api/auth/email/verify',json={'email':email,'code':code}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:verify(),range(2)))
        self.assertEqual(sorted(results),[200,401])

if __name__ == '__main__': unittest.main()
