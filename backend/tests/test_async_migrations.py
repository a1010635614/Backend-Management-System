import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys

import asyncpg
import pytest


async def test_upgrade_preserves_legacy_articles_users_and_attachments(isolated):
    url = os.getenv('UPGRADE_DATABASE_URL')
    assert url and re.fullmatch(r'postgresql\+asyncpg://blog_test@127\.0\.0\.1:[0-9]+/upgradecheck', url)
    env = {**os.environ, 'DATABASE_URL': url}

    async def migrate(*args):
        stage = ' '.join(args)
        print('Legacy migration check: ' + stage, flush=True)
        # The CLI is synchronous in production too. Keep its wait/kill handling
        # independent of the test runner's session-scoped asyncio child watcher.
        def run():
            return subprocess.run([sys.executable, '-m', 'alembic', *args],
                cwd=Path(__file__).resolve().parents[1], env=env,
                capture_output=True, timeout=25)
        try:
            result = await asyncio.wait_for(asyncio.to_thread(run), timeout=35)
        except subprocess.TimeoutExpired as error:
            pytest.fail('Alembic subprocess timed out at '+stage+'\n'+
                        ((error.stdout or b'')+(error.stderr or b'')).decode(errors='replace'))
        assert result.returncode == 0, (result.stdout + result.stderr).decode(errors='replace')
        print('Legacy migration completed: ' + stage, flush=True)

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
