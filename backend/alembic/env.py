import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import Base
import app.models  # Register all model metadata, without importing the HTTP application.

target_metadata = Base.metadata


def migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(get_settings().database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        # A database-level session lock also serializes separate migration hosts.
        await connection.execute(text('SELECT pg_advisory_lock(1112297287)'))
        await connection.commit()
        try:
            await connection.run_sync(migrations)
        finally:
            await connection.rollback()
            await connection.execute(text('SELECT pg_advisory_unlock(1112297287)'))
            await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                       literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
