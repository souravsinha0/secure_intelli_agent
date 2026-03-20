"""
app/database.py
───────────────
Async SQLAlchemy setup + ORM models.
All state that must survive a server restart is stored here:
  - chat_sessions   — session metadata
  - chat_messages   — individual messages + defense scan results
  - request_logs    — raw request/response audit trail (for AI Defense red-team)
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import get_settings

settings = get_settings()

# ── Make sure the URL uses the async driver ──────────────────────────────────
_db_url = settings.database_url
if _db_url.startswith("sqlite:///") and "aiosqlite" not in _db_url:
    _db_url = _db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

engine = create_async_engine(
    _db_url,
    echo=settings.app_debug,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


# ── ORM Models ───────────────────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id          = Column(String, primary_key=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    model       = Column(String, nullable=True)
    provider    = Column(String, nullable=True)
    messages    = relationship("ChatMessage", back_populates="session", lazy="selectin")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    session_id      = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    role            = Column(String, nullable=False)          # user | assistant | system
    content         = Column(Text,   nullable=False)
    # Defense scan result
    defense_checked = Column(Boolean, default=False)
    defense_safe    = Column(Boolean, nullable=True)
    defense_severity= Column(String, nullable=True)
    defense_detail  = Column(JSON,   nullable=True)           # full InspectResponse
    # LLM metadata
    model_used      = Column(String, nullable=True)
    prompt_tokens   = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    session = relationship("ChatSession", back_populates="messages")


class RequestLog(Base):
    """
    Stores every inbound /v1/chat/completions call raw — used for:
      • Audit trail
      • AI Defense red-team / attack validation replay
    """
    __tablename__ = "request_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source_ip       = Column(String, nullable=True)
    request_body    = Column(JSON,   nullable=True)
    response_body   = Column(JSON,   nullable=True)
    http_status     = Column(Integer, nullable=True)
    defense_input_result  = Column(JSON, nullable=True)
    defense_output_result = Column(JSON, nullable=True)
    latency_ms      = Column(Float,  nullable=True)
    blocked         = Column(Boolean, default=False)
    block_stage     = Column(String, nullable=True)   # "input" | "output" | None


# ── DB lifecycle helpers ──────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables (idempotent — safe to call on every startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields an async session."""
    async with AsyncSessionLocal() as session:
        yield session
