import asyncio
import os
from pathlib import Path
import sys

import asyncpg
import pytest


async def test_upgrade_preserves_legacy_articles_users_and_attachments(isolated):
    url = os.getenv('UPGRADE_DATABASE_URL')
    assert url and url.startswith('postgresql+asyncpg://blog_test@127.0.0.1:')
    env = {**os.environ, 'DATABASE_URL': url}

    async def migrate(*args):
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'alembic', *args,
            cwd=Path(__file__).resolve().parents[1], env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, error = await process.communicate()
        assert process.returncode == 0, (out + error).decode(errors='replace')

    await migrate('upgrade', '0002')
    dsn = url.replace('postgresql+asyncpg://', 'postgresql://', 1)
    connection = await asyncpg.connect(dsn)
    try:
        user = await connection.fetchval("INSERT INTO users(email) VALUES('legacy@example.com') RETURNING id")
        post = await connection.fetchval("INSERT INTO posts(title,summary,content,category,read_minutes,views,likes) VALUES('旧文章','旧摘要','原始正文','技术',1,9,2) RETURNING id")
        await connection.execute("INSERT INTO assets(id,key,filename,content_type,size,owner_id,state) VALUES('f7b273ca-25f4-47bf-b1b7-010781746c61','uploads/legacy.png','旧图片.png','image/png',12,$1,'ready')", user)
    finally:
        await connection.close()
    await migrate('upgrade', 'head')
    await migrate('check')
    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow('SELECT * FROM posts WHERE id=$1', post)
        assert row['content'] == '原始正文' and row['views'] == 9 and row['status'] == 'published'
        assert row['updated_at'] == row['created_at']
        assert await connection.fetchval('SELECT role FROM users WHERE id=$1', user) == 'viewer'
        assert await connection.fetchval('SELECT count(*) FROM assets') == 1
    finally:
        await connection.close()
    await migrate('downgrade', '0002')
    connection = await asyncpg.connect(dsn)
    try:
        assert await connection.fetchval('SELECT content FROM posts WHERE id=$1', post) == '原始正文'
        assert await connection.fetchval('SELECT count(*) FROM assets') == 1
    finally:
        await connection.close()
    await migrate('upgrade', 'head')
