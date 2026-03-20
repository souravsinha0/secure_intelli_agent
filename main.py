"""
main.py
────────
Velocis Intelli Agent — FastAPI entry point.

Startup order:
  1. Load settings from .env
  2. Initialise SQLite database (create tables if missing)
  3. Mount static assets + Jinja2 templates
  4. Register routers (chat, config)
  5. Optionally start ngrok tunnel
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import init_db
from app.routers import chat, config as config_router

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("velocis")

settings = get_settings()


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("Velocis Intelli Agent starting up…")
    await init_db()
    logger.info("Database initialised at %s", settings.database_url)

    ngrok_url = None
    if settings.ngrok_authtoken and settings.ngrok_authtoken != "your-ngrok-auth-token-here":
        ngrok_url = _start_ngrok()

    if ngrok_url:
        logger.info("=" * 60)
        logger.info("  🌐  Public URL  :  %s", ngrok_url)
        logger.info("  👉  AI Defense red-team endpoint:")
        logger.info("      %s/v1/chat/completions", ngrok_url)
        logger.info("=" * 60)
    else:
        logger.info("ngrok not configured — running locally only")
        logger.info("Local URL: http://%s:%s", settings.app_host, settings.app_port)

    yield

    # ── Shutdown ──
    logger.info("Shutting down Velocis Intelli Agent.")


def _start_ngrok() -> str | None:
    """Start ngrok tunnel and return the public URL."""
    try:
        from pyngrok import ngrok, conf

        conf.get_default().auth_token = settings.ngrok_authtoken

        options: dict = {"addr": settings.app_port}
        if settings.ngrok_domain:
            options["hostname"] = settings.ngrok_domain

        tunnel = ngrok.connect(**options)
        public_url: str = tunnel.public_url  # type: ignore[attr-defined]

        # Prefer https
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)

        return public_url
    except Exception as exc:
        logger.warning("ngrok failed to start: %s", exc)
        return None


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Velocis Intelli Agent",
    description=(
        "Secure AI chat with Cisco AI Defense guardrails. "
        "Drop-in OpenAI-compatible endpoint — "
        "use /v1/chat/completions as the AI Defense attack-validation target."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Templates ─────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory="templates")

# ── Static files (if you add CSS/JS assets later) ────────────────────────────
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(chat.router, tags=["Chat"])
app.include_router(config_router.router, tags=["Config"])


# ── Frontend ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend(request: Request):
    """Serve the single-page chatbot UI."""
    return templates.TemplateResponse("index.html", {"request": request})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="debug" if settings.app_debug else "info",
    )
