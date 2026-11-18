"""仅用于本机预览：隔离 SQLite 数据库、示例文章及一次性登录码。"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256

ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.update(DATABASE_URL="sqlite:///"+(ROOT/".preview.db").as_posix(),ADMIN_EMAILS="preview@example.com",JWT_SECRET="local-preview-"+secrets.token_hex(32),GEETEST_ID="",GEETEST_KEY="",MAIL_HOST="",COS_SECRET_ID="",COS_SECRET_KEY="",BAIDU_HM_ID="")
subprocess.run([sys.executable,"-m","alembic","upgrade","head"],check=True)
from app.main import Post,Code,SessionLocal,settings,app
from sqlalchemy import select

code=f"{secrets.randbelow(1000000):06d}"
with SessionLocal() as db:
    if not db.scalar(select(Post.id).limit(1)):
        for title,summary,content,category in [
            ("在慢下来的日子里，重新认识生活","我们总在赶路，却忘了看看沿途。给自己留一点不被安排的时间。","周末的清晨，我把手机留在了书桌上。\n\n走到河边的时候，太阳刚刚越过树梢。原来生活里一直有许多值得停留的时刻，只是我们很少抬头。\n\n给自己一点空白，听风，看云，让日子慢慢展开。","生活随笔"),
            ("秋天的第一封信，写给很久以后的自己","风很轻，心里装着许多小小的期待。","如果未来的你读到这封信，希望你还记得这个普通的下午。\n\n窗外的叶子开始变黄，桌上有一杯温热的茶。我们不必每一天都做出了不起的事，也可以认真地过好一个平凡的日子。","手记"),
            ("把阅读变成一种温柔的习惯","在另一个人的思想里坐一会儿，听听不同的生活如何展开。","读书并不总是为了得到答案。\n\n每天睡前留出二十分钟，翻开一本喜欢的书。那些读过的句子会在某一个瞬间回到心里，为生活添上一点光。","阅读札记")]:
            db.add(Post(title=title,summary=summary,content=content,category=category,read_minutes=3,views=0,likes=0))
    db.add(Code(email="preview@example.com",digest=sha256(("preview@example.com"+code+settings.jwt_secret).encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
    db.commit()
print(f"LOCAL PREVIEW LOGIN: preview@example.com / {code} (one use, 1 hour)",flush=True)
import uvicorn
uvicorn.run(app,host="127.0.0.1",port=8000)
