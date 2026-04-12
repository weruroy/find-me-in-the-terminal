"""
Find me in the terminal — FastAPI Application
═══════════════════════════════════════════════
Entry point. Serves the landing page HTML and wires up all API routers.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config   import get_settings
from app.database import init_db
from app.routers  import subscribers, emails

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log      = logging.getLogger(__name__)
settings = get_settings()

# ── Templates ──────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀  Starting up — %s", settings.APP_NAME)
    await init_db()
    log.info("✅  Database tables verified / created")
    yield
    log.info("👋  Shutting down")


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = settings.APP_NAME,
    description = "Newsletter backend for Find me in the terminal",
    version     = "1.0.0",
    docs_url    = "/api/docs",
    redoc_url   = "/api/redoc",
    lifespan    = lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],   # tighten to your domain in production
    allow_methods  = ["*"],
    allow_headers  = ["*"],
    allow_credentials = True,
)

# ── Static files (CSS/JS/images if you add them later) ────────────────────
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(subscribers.router)
app.include_router(emails.router)


# ── Landing page ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Serve the HTML landing page as a Jinja2 template."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request":  request,
            "app_name": settings.APP_NAME,
            "app_url":  settings.APP_URL,
        },
    )


# ── Unsubscribe page ───────────────────────────────────────────────────────
@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_page(request: Request, token: str = ""):
    """
    Handles the one-click unsubscribe link in emails.
    Delegates to the subscriber router's token-based unsubscribe.
    """
    from sqlalchemy import select, update
    from app.database import AsyncSessionLocal
    from app.models   import Subscriber, SubscriberStatus
    from datetime import datetime

    message = "Something went wrong. Please try again."
    success = False

    if token:
        async with AsyncSessionLocal() as db:
            sub = await db.scalar(
                select(Subscriber).where(Subscriber.unsubscribe_token == token)
            )
            if sub and sub.status == SubscriberStatus.ACTIVE:
                sub.status          = SubscriberStatus.UNSUBSCRIBED
                sub.unsubscribed_at = datetime.utcnow()
                await db.commit()
                message = "You've been successfully unsubscribed."
                success = True
            elif sub and sub.status == SubscriberStatus.UNSUBSCRIBED:
                message = "You were already unsubscribed."
                success = True
            else:
                message = "Invalid or expired unsubscribe link."

    return templates.TemplateResponse(
        "unsubscribe.html",
        {"request": request, "message": message, "success": success, "app_url": settings.APP_URL},
    )


# ── Privacy page ───────────────────────────────────────────────────────────
@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "app_name": settings.APP_NAME})


# ── Health check ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


# ── Global exception handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)