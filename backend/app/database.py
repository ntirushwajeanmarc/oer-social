from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def apply_schema_patches(connection) -> None:
    """Add columns/indexes create_all will not apply to existing tables."""
    await connection.execute(
        text(
            "ALTER TABLE ai_projects "
            "ADD COLUMN IF NOT EXISTS source_project_id VARCHAR(120) DEFAULT ''"
        )
    )
    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_projects_admin_source "
            "ON ai_projects (admin_id, source_project_id) "
            "WHERE source_project_id IS NOT NULL AND source_project_id <> ''"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE admin_memory_conversations "
            "ADD COLUMN IF NOT EXISTS source_project_id VARCHAR(120) DEFAULT ''"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE admin_memory_conversations "
            "ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)"
        )
    )
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_admin_memory_conversations_project_id "
            "ON admin_memory_conversations (project_id)"
        )
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
