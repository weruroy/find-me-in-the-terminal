from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────
    APP_NAME: str = "Find me in the terminal"
    APP_URL:  str = "http://localhost:8000"
    DEBUG:    bool = False

    # ── Neon PostgreSQL (async) ────────────────────────────────────────
    # Format: postgresql+asyncpg://user:password@host/dbname?sslmode=require
    DATABASE_URL: str

    # ── SMTP / Email ───────────────────────────────────────────────────
    SMTP_HOST:     str = "smtp.gmail.com"
    SMTP_PORT:     int = 587
    SMTP_USER:     str
    SMTP_PASSWORD: str           # Gmail App Password (16 chars)
    FROM_NAME:     str = "Find me in the terminal"
    FROM_EMAIL:    str

    # ── Security ───────────────────────────────────────────────────────
    SECRET_KEY:       str = "change-me-in-production-use-openssl-rand-hex-32"
    UNSUBSCRIBE_SALT: str = "unsubscribe-salt-change-me"

    # ── Rate limiting ──────────────────────────────────────────────────
    MAX_SUBSCRIBE_PER_IP_PER_HOUR: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
