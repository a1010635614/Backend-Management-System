from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac, os, secrets
from typing import Optional
import httpx
from qcloud_cos import CosConfig, CosS3Client
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, String, Text, Integer, BigInteger, DateTime, Boolean, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
    database_url:str="postgresql+psycopg://blog:blog@localhost:5432/blog"
    jwt_secret:str="development-only-change-this-secret-key"
    jwt_exp_minutes:int=60
    mail_host:str=""; mail_port:int=587; mail_username:str=""; mail_password:str=""; mail_from:str="noreply@example.com"
    geetest_id:str=""; geetest_key:str=""
    cos_secret_id:str=""; cos_secret_key:str=""; cos_region:str="ap-shanghai"; cos_bucket:str=""; cos_public_base_url:str=""
settings=Settings(); engine=create_engine(settings.database_url,pool_pre_ping=True); SessionLocal=sessionmaker(bind=engine,expire_on_commit=False); oauth=HTTPBearer(auto_error=False)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True); email:Mapped[str]=mapped_column(String(320),unique=True,index=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class Post(Base):
    __tablename__="posts"
    id:Mapped[int]=mapped_column(primary_key=True); title:Mapped[str]=mapped_column(String(180)); summary:Mapped[str]=mapped_column(String(500)); content:Mapped[str]=mapped_column(Text); category:Mapped[str]=mapped_column(String(60),default="生活随笔"); read_minutes:Mapped[int]=mapped_column(Integer,default=1); views:Mapped[int]=mapped_column(BigInteger,default=0); likes:Mapped[int]=mapped_column(BigInteger,default=0); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class Event(Base):
    __tablename__="analytics_events"
    id:Mapped[int]=mapped_column(primary_key=True); event_name:Mapped[str]=mapped_column(String(80)); path:Mapped[str]=mapped_column(String(500)); visitor_id:Mapped[Optional[str]]=mapped_column(String(100)); referrer:Mapped[Optional[str]]=mapped_column(String(1000)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class Code(Base):
    __tablename__="email_codes"
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    id:Mapped[int]=mapped_column(primary_key=True); email:Mapped[str]=mapped_column(String(320),index=True); digest:Mapped[str]=mapped_column(String(64)); expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); used:Mapped[bool]=mapped_column(Boolean,default=False)
app=FastAPI(title="纸间博客 API",version="1.0.0",description="博客、认证、COS 上传及业务分析")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","http://localhost:5173").split(","),allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
class PostIn(BaseModel): title:str=Field(min_length=1,max_length=180); summary:str=Field(min_length=1,max_length=500); content:str=Field(min_length=1); category:str=Field(default="生活随笔",max_length=60)
class EmailIn(BaseModel): email:EmailStr; geetest:dict[str,str]=Field(default_factory=dict)
class VerifyIn(EmailIn): code:str=Field(pattern=r"^\d{6}$")
class TrackIn(BaseModel): event:str=Field(min_length=1,max_length=80); path:str=Field(min_length=1,max_length=500); visitorId:Optional[str]=Field(default=None,max_length=100); referrer:Optional[str]=Field(default=None,max_length=1000)
def check_geetest(payload:dict):
    if not settings.geetest_id or not settings.geetest_key: raise HTTPException(503,"极验尚未配置")
    if not {"lot_number","captcha_output","pass_token","gen_time"}.issubset(payload): raise HTTPException(400,"极验参数不完整")
    sign=hmac.new(settings.geetest_key.encode(),payload["lot_number"].encode(),sha256).hexdigest()
    try: data=httpx.post(os.getenv("GEETEST_VERIFY_URL","https://gcaptcha4.geetest.com/validate"),params={"captcha_id":settings.geetest_id},data={**payload,"sign_token":sign},timeout=8).json()
    except Exception: raise HTTPException(502,"极验服务暂不可用")
    if data.get("result")!="success": raise HTTPException(401,"极验校验未通过")
@app.get("/api/health")
def health(db:Session=Depends(get_db)):
    db.execute(select(User.id).limit(1));return {"status":"UP"}
@app.get("/api/public/config")
def public_config(): return {"baiduId":os.getenv("BAIDU_HM_ID","")}
@app.get("/api/posts")
def posts(db:Session=Depends(get_db)):
    return [{"id":p.id,"title":p.title,"summary":p.summary,"category":p.category,"cover":"photo-1470252649378-9c29740c9fa8","readMinutes":p.read_minutes,"views":p.views,"likes":p.likes,"createdAt":p.created_at.strftime("%Y.%m.%d") if p.created_at else ""} for p in db.scalars(select(Post).order_by(Post.created_at.desc())).all()]
@app.get("/api/posts/{post_id}")
def post_detail(post_id:int,db:Session=Depends(get_db)):
    p=db.get(Post,post_id)
    if not p: raise HTTPException(404,"文章不存在")
    return {"id":p.id,"title":p.title,"summary":p.summary,"content":p.content,"category":p.category,"createdAt":p.created_at}
def current_user(credentials:Optional[HTTPAuthorizationCredentials]=Depends(oauth),db:Session=Depends(get_db)):
    if not credentials: raise HTTPException(401,"请先登录",headers={"WWW-Authenticate":"Bearer"})
    try: email=jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=["HS256"],options={"require_exp":True,"require_sub":True})["sub"]
    except (JWTError,KeyError): raise HTTPException(401,"登录已失效")
    user=db.scalar(select(User).where(User.email==email))
    if not user: raise HTTPException(401,"用户不存在")
    return user
def admin_user(user:User=Depends(current_user)):
    allowed={email.strip().lower() for email in os.getenv("ADMIN_EMAILS","").split(",") if email.strip()}
    if user.email.lower() not in allowed: raise HTTPException(403,"需要管理员权限")
    return user
@app.get("/api/auth/config")
def auth_config(): return {"captchaId":settings.geetest_id}
@app.get("/api/auth/me")
def me(user:User=Depends(admin_user)): return {"email":user.email}
@app.put("/api/posts/{post_id}")
def update_post(post_id:int,body:PostIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    p=db.get(Post,post_id)
    if not p: raise HTTPException(404,"文章不存在")
    for key,value in body.model_dump().items(): setattr(p,key,value)
    p.read_minutes=max(1,len(body.content)//500);db.commit();return {"id":p.id}
@app.delete("/api/posts/{post_id}",status_code=204)
def delete_post(post_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    p=db.get(Post,post_id)
    if not p: raise HTTPException(404,"文章不存在")
    db.delete(p);db.commit()
@app.post("/api/posts",status_code=201)
def create_post(body:PostIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    p=Post(**body.model_dump(),read_minutes=max(1,len(body.content)//500));db.add(p);db.commit();db.refresh(p);return {"id":p.id,"title":p.title}
@app.post("/api/auth/email/send",status_code=202)
def send_code(body:EmailIn,db:Session=Depends(get_db)):
    if not settings.mail_host: raise HTTPException(503,"邮件服务尚未配置")
    if settings.geetest_id: check_geetest(body.geetest)
    # PostgreSQL 事务级锁覆盖该邮箱的检查、邮件发送和提交，避免并发重复发信。
    if db.bind.dialect.name=="postgresql":
        from sqlalchemy import text
        lock_id=int.from_bytes(sha256(str(body.email).encode()).digest()[:8],"big",signed=True)
        db.execute(text("select pg_advisory_xact_lock(:lock_id)"),{"lock_id":lock_id})
    latest=db.scalar(select(Code).where(Code.email==body.email,Code.expires_at>datetime.now(timezone.utc)).order_by(Code.id.desc()))
    if latest: raise HTTPException(429,"验证码已发送，五分钟后可重发")
    code=f"{secrets.randbelow(1000000):06d}";digest=sha256((body.email+code+settings.jwt_secret).encode()).hexdigest()
    db.add(Code(email=body.email,digest=digest,expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))
    from email.message import EmailMessage
    from app.mailer import send_message
    msg=EmailMessage();msg["Subject"]="纸间博客登录验证码";msg["From"]=settings.mail_from;msg["To"]=body.email;msg.set_content(f"您的验证码是 {code}，5 分钟内有效。")
    try:
        send_message(msg,settings)
    except Exception: raise HTTPException(502,"验证码邮件发送失败")
    db.commit();return {"message":"验证码已发送"}
@app.post("/api/auth/email/verify")
def verify_code(body:VerifyIn,db:Session=Depends(get_db)):
    rec=db.scalar(select(Code).where(Code.email==body.email,Code.used.is_(False),Code.expires_at>datetime.now(timezone.utc)).order_by(Code.id.desc()).with_for_update())
    digest=sha256((body.email+body.code+settings.jwt_secret).encode()).hexdigest()
    if not rec: raise HTTPException(401,"验证码错误或已过期")
    if rec.attempts>=5: raise HTTPException(429,"验证码尝试次数已用尽")
    rec.attempts+=1
    if not hmac.compare_digest(rec.digest,digest):
        db.commit();raise HTTPException(401,"验证码错误或已过期")
    rec.used=True;user=db.scalar(select(User).where(User.email==body.email))
    if not user: user=User(email=body.email);db.add(user)
    db.commit();token=jwt.encode({"sub":user.email,"exp":datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_exp_minutes)},settings.jwt_secret,algorithm="HS256");return {"access_token":token,"token_type":"bearer","expires_in":settings.jwt_exp_minutes*60}
@app.post("/api/uploads/presign")
def presign(filename:str,content_type:str,user:User=Depends(admin_user)):
    if not all((settings.cos_bucket,settings.cos_secret_id,settings.cos_secret_key)): raise HTTPException(503,"COS 尚未配置")
    if content_type not in {"image/jpeg","image/png","image/webp","application/pdf"}: raise HTTPException(400,"不支持的文件类型")
    extensions={"image/jpeg":"jpg","image/png":"png","image/webp":"webp","application/pdf":"pdf"}
    key=f"uploads/{user.id}/{secrets.token_hex(16)}.{extensions[content_type]}"
    client=CosS3Client(CosConfig(Region=settings.cos_region,SecretId=settings.cos_secret_id,SecretKey=settings.cos_secret_key,Scheme="https"))
    url=client.get_presigned_url(Bucket=settings.cos_bucket,Key=key,Method="PUT",Expired=300,Headers={"Content-Type":content_type})
    public_url=f"{settings.cos_public_base_url.rstrip('/')}/{key}" if settings.cos_public_base_url else ""
    return {"uploadUrl":url,"key":key,"publicUrl":public_url}
@app.post("/api/analytics/events",status_code=202)
def collect(body:TrackIn,db:Session=Depends(get_db)):
    db.add(Event(event_name=body.event,path=body.path,visitor_id=body.visitorId,referrer=body.referrer));db.commit();return {"status":"accepted"}
@app.get("/api/analytics/summary")
def summary(db:Session=Depends(get_db),user:User=Depends(admin_user)):
    today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    pv,uv=db.execute(select(func.count(Event.id),func.count(func.distinct(Event.visitor_id))).where(Event.created_at>=today,Event.event_name=="pageview")).one();return {"pv":pv,"uv":uv}
