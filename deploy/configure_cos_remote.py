"""Called only by configure_cos.py's SSH bootstrap, with environment helpers bound."""
import base64
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import urlsplit,urlunsplit
import httpx
from qcloud_cos import CosConfig,CosS3Client

def main():
    credentials=json.load(sys.stdin)
    bucket='kongqi-agent-1317119844';region='ap-shanghai'
    envpath=Path('/etc/vueblog.env')
    original=envpath.read_bytes();owner=envpath.stat()
    updates={'COS_BUCKET':bucket,'COS_REGION':region,'COS_SECRET_ID':credentials['secret_id'],'COS_SECRET_KEY':credentials['secret_key']}
    content=serialize_environment(original.decode(),updates).encode()
    key='uploads/verification/'+secrets.token_hex(16)+'.png'
    image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1sAAAAASUVORK5CYII=')
    client=CosS3Client(CosConfig(Region=region,SecretId=updates['COS_SECRET_ID'],SecretKey=updates['COS_SECRET_KEY'],Scheme='https',Timeout=10))
    phase='upload'
    try:
        client.put_object(Bucket=bucket,Key=key,Body=image,ContentType='image/png')
        phase='HEAD metadata'
        metadata={k.lower():v for k,v in client.head_object(Bucket=bucket,Key=key).items()}
        if int(metadata['content-length'])!=len(image): raise ValueError('Object size mismatch')
        signed=client.get_presigned_url(Bucket=bucket,Key=key,Method='GET',Expired=120)
        with httpx.Client(timeout=12) as web:
            phase='signed download'
            response=web.get(signed);response.raise_for_status()
            if response.content!=image: raise ValueError('Downloaded bytes mismatch')
            parts=urlsplit(signed)
            unsigned=urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))
            phase='private bucket access check'
            if web.get(unsigned).status_code!=403: raise ValueError('Bucket must deny unsigned object reads')
            put=client.get_presigned_url(Bucket=bucket,Key=key,Method='PUT',Expired=120,Headers={'Content-Type':'image/png','Content-Length':str(len(image))})
            try:
                cors=web.options(put,headers={'Origin':'http://127.0.0.1:5173','Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'content-type'})
                cors_ready=cors.status_code<400 and cors.headers.get('access-control-allow-origin') in ('http://127.0.0.1:5173','*') and 'PUT' in cors.headers.get('access-control-allow-methods','')
            except httpx.RequestError:
                cors_ready=False
    except Exception as error:
        code=error.get_status_code() if hasattr(error,'get_status_code') else type(error).__name__
        raise SystemExit('COS '+phase+' failed ('+str(code)+'); server configuration was not changed. A small verification object may remain under uploads/verification/.') from None
    print('COS upload, HEAD metadata, signed download, private read: PASS',flush=True)
    try:
        replace_file(envpath,content,owner)
        subprocess.run(['systemctl','restart','vueblog'],check=True,capture_output=True)
        for attempt in range(15):
            try:
                response=httpx.get('http://127.0.0.1:8000/api/health',timeout=2);response.raise_for_status();break
            except Exception:
                if attempt==14: raise RuntimeError('Health failed')
                time.sleep(1)
    except Exception:
        replace_file(envpath,original,owner)
        subprocess.run(['systemctl','restart','vueblog'],capture_output=True)
        raise SystemExit('Application configuration failed and was restored; check service health.') from None
    print('COS credentials installed on server; API health: PASS')
    print('Browser CORS: '+('PASS' if cors_ready else 'NOT READY - allow Origin http://127.0.0.1:5173, method PUT, header Content-Type in COS console'))
    print('Private verification object retained for inspection: '+key)

if __name__=='__main__': main()
