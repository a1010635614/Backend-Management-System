import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy/scripts'))
from database_tools import DatabaseError, PostgresClient


async def test_custom_backup_restores_exact_rows_and_rejects_overwrite(isolated, tmp_path):
    source_url, target_url = os.environ.get('BACKUP_DATABASE_URL', ''), os.environ.get('RESTORE_DATABASE_URL', '')
    match = re.fullmatch(r'postgresql\+asyncpg://blog_test@127\.0\.0\.1:([0-9]+)/backupsource', source_url)
    assert match and target_url == source_url.replace('/backupsource', '/backuprestore')
    port = int(match[1])
    assert port > 1024 and port != 5432
    env = {**os.environ, 'DATABASE_URL': source_url}
    result = await asyncio.to_thread(subprocess.run,
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, timeout=30)
    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors='replace')
    connection = await asyncpg.connect(source_url.replace('postgresql+asyncpg://', 'postgresql://'), timeout=5)
    try:
        user = await connection.fetchval("INSERT INTO users(email,role) VALUES('restore@example.com','editor') RETURNING id")
        await connection.execute("INSERT INTO posts(title,summary,content,category,read_minutes,views,likes,author_id) "
            "VALUES($1,$2,$3,'技术',2,17,3,$4)", '恢复核验', '正文与附件保持不变', '# 中文标题\n\n包含单引号 \' 和 Markdown。', user)
        await connection.execute("INSERT INTO assets(id,key,filename,content_type,size,owner_id,state) "
            "VALUES('f7b273ca-25f4-47bf-b1b7-010781746c61','uploads/restore.png','恢复.png','image/png',12,$1,'ready')", user)
        await connection.execute("INSERT INTO analytics_events(event_name,path,visitor_id) VALUES('pageview','/posts/1','restore-fixture')")
    finally:
        await connection.close()
    settings = {'bin_dir': os.environ['POSTGRES_BIN'], 'host': '127.0.0.1', 'port': port}
    source = PostgresClient([], 'blog_test', 'backupsource', **settings)
    target = PostgresClient([], 'blog_test', 'backuprestore', **settings)
    expected = await asyncio.to_thread(source.fingerprint)
    archive = tmp_path / 'fixture.dump'
    metadata = await asyncio.to_thread(source.dump, archive, source_commit='a' * 40)
    restored = await asyncio.to_thread(target.restore_empty, archive, metadata)
    assert restored == expected
    assert restored['users']['count'] == restored['posts']['count'] == restored['assets']['count'] == 1
    with pytest.raises(DatabaseError, match='not empty'):
        await asyncio.to_thread(target.restore_empty, archive, metadata)
    assert await asyncio.to_thread(target.fingerprint) == expected
    corrupt = tmp_path / 'corrupt'; corrupt.mkdir()
    changed = corrupt / archive.name
    changed.write_bytes(archive.read_bytes() + b'changed')
    with pytest.raises(DatabaseError, match='digest'):
        await asyncio.to_thread(target.restore_empty, changed, metadata)
