from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app.config import settings
from app.database import Base, SessionLocal, apply_schema_patches, engine
from app.models import User
from app.routers import auth, packs, program_brief, submissions, workspace
from app.services.program_brief import seed_initial_brief
from app.services.security import hash_password

logger = logging.getLogger("oer")


async def bootstrap_admin() -> None:
    email = settings.bootstrap_admin_email.lower().strip()
    password = settings.bootstrap_admin_password
    if not email or not password:
        logger.warning(
            "Bootstrap admin skipped: set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in backend/.env"
        )
        return
    if len(password) < 8:
        logger.error("Bootstrap admin skipped: BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters")
        return

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    name=settings.bootstrap_admin_name or "OER Admin",
                    role="admin",
                    cadre="Educator",
                    site="OER Platform",
                )
            )
            await db.commit()
            logger.info("Bootstrap admin created for %s", email)
            return

        if settings.bootstrap_admin_sync:
            user.password_hash = hash_password(password)
            user.role = "admin"
            if settings.bootstrap_admin_name:
                user.name = settings.bootstrap_admin_name
            await db.commit()
            logger.info("Bootstrap admin credentials synced for %s", email)


async def bootstrap_program_brief() -> None:
    email = settings.bootstrap_admin_email.lower().strip()
    if not email:
        return
    async with SessionLocal() as db:
        admin = await db.scalar(select(User).where(User.email == email))
        if admin and admin.role == "admin":
            await seed_initial_brief(db, admin)


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_admin_memory_search "
                "ON admin_memory_conversations USING GIN "
                "(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(user_text, '')))"
            )
        )
        # Cosine ANN index for CircuitNotion embeddings (text-embedding-3-small = 1536d)
        try:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_admin_memory_chunks_embedding "
                    "ON admin_memory_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pgvector HNSW index not ready yet: %s", exc)
        await conn.execute(
            text(
                "ALTER TABLE content_packs "
                "ADD COLUMN IF NOT EXISTS poster_image_path VARCHAR(500) DEFAULT ''"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE social_posts "
                "ADD COLUMN IF NOT EXISTS error_message TEXT DEFAULT ''"
            )
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS education_level VARCHAR(120) DEFAULT ''")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_years INTEGER DEFAULT 0")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS learning_goals TEXT DEFAULT ''")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS topics_of_interest TEXT DEFAULT ''")
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "preferred_language VARCHAR(80) DEFAULT 'English'"
            )
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS local_context TEXT DEFAULT ''")
        )
        await conn.execute(
            text("ALTER TABLE content_packs ALTER COLUMN topic TYPE TEXT")
        )
        await conn.execute(
            text(
                "ALTER TABLE ai_messages "
                "ADD COLUMN IF NOT EXISTS image_path VARCHAR(500) DEFAULT ''"
            )
        )
        await apply_schema_patches(conn)
        Path(settings.media_dir, "chat").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.jwt_secret or settings.jwt_secret in (
        "change-me",
        "oer-social-dev-jwt-secret-change-me",
    ):
        logger.warning("JWT_SECRET is weak or unset — set a long random value in backend/.env for production")

    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.media_dir, "posters").mkdir(parents=True, exist_ok=True)

    await ensure_schema()
    await bootstrap_admin()
    await bootstrap_program_brief()

    async def _embed_backfill() -> None:
        if not settings.memory_embed_enabled:
            return
        try:
            from app.services.memory_index import backfill_memory_embeddings

            stats = await backfill_memory_embeddings(batch_conversations=6)
            logger.info("Admin memory embedding backfill: %s", stats)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Admin memory embedding backfill failed: %s", exc)

    asyncio.create_task(_embed_backfill())
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_origin_regex=r"https://.*\.ngrok(-free)?\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

api = settings.api_prefix
app.include_router(auth.router, prefix=api)
app.include_router(packs.router, prefix=api)
app.include_router(program_brief.router, prefix=api)
app.include_router(submissions.router, prefix=api)
app.include_router(workspace.router, prefix=api)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
