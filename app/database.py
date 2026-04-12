from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings
import os
from dotenv import load_dotenv
load_dotenv()

settings = get_settings()
#Formart the DB connection string to have the correct connection format
def _build_async_url() -> str:
    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        raise ValueError("DATABASE_URL environment variable is not set")

    base = raw.split("?")[0]

    # Strip any existing driver prefix and replace with asyncpg
    for prefix in [
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgresql+asyncpg://",
        "postgresql://",
        "postgres://",          # Neon/Heroku sometimes use this
    ]:
        if base.startswith(prefix):
            host_part = base[len(prefix):]
            return f"postgresql+asyncpg://{host_part}"

    raise ValueError(f"Unrecognized DATABASE_URL scheme: {base}")

# ── Engine ─────────────────────────────────────────────────────────────────
# Neon requires sslmode=require — already embedded in DATABASE_URL
engine = create_async_engine(
    _build_async_url(),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # detect stale Neon connections
    pool_recycle=300,     # recycle every 5 min (Neon idles connections)
    echo=settings.DEBUG,
)

# ── Session factory ────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base model ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency — FastAPI route injection ──────────────────────────────────
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Create tables on startup ───────────────────────────────────────────────
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
