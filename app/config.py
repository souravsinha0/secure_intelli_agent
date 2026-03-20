"""
app/config.py
─────────────
Centralised settings loaded from .env via pydantic-settings.
All runtime configuration lives here — no scattered os.getenv() calls.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────
    app_host: str = Field("0.0.0.0", description="Bind host")
    app_port: int = Field(8080, description="Bind port")
    app_debug: bool = Field(False, description="Enable debug mode")
    app_secret_key: str = Field("change-me", description="App secret key")

    # ── Cisco AI Defense ──────────────────────────────────
    ai_defense_mode: str = Field("api", description="'api' or 'gateway'")
    ai_defense_api_key: str = Field("", description="AI Defense API key")
    ai_defense_base_url: str = Field(
        "https://us.api.inspect.aidefense.security.cisco.com",
        description="AI Defense regional base URL",
    )
    ai_defense_timeout_ms: int = Field(15000, description="Request timeout in ms")

    # ── LLM ───────────────────────────────────────────────
    llm_provider: str = Field("openai", description="openai|google|anthropic|onprem")
    llm_api_key: str = Field("", description="LLM provider API key")
    llm_model: str = Field("gpt-4o", description="Model name")
    llm_max_tokens: int = Field(2048, description="Max response tokens")
    llm_temperature: float = Field(0.7, description="Sampling temperature")

    # ── On-Prem Model ─────────────────────────────────────
    onprem_model_name: str = Field("gpt-oss-20b", description="On-prem model name")
    onprem_base_url: str = Field(
        "http://10.52.1.13:8000/v1", description="On-prem OpenAI-compatible base URL"
    )
    onprem_api_key: str = Field("", description="On-prem server API key (if any)")

    # ── ngrok ─────────────────────────────────────────────
    ngrok_authtoken: str = Field("", description="ngrok auth token")
    ngrok_domain: str = Field("", description="Optional fixed ngrok domain")

    # ── Database ──────────────────────────────────────────
    database_url: str = Field("sqlite+aiosqlite:///./velocis.db")

    # ── CORS ──────────────────────────────────────────────
    cors_origins: str = Field("*", description="Comma-separated allowed origins")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_defense_inspect_url(self) -> str:
        """Full AI Defense inspect endpoint URL."""
        base = self.ai_defense_base_url.rstrip("/")
        return f"{base}/api/v1/inspect/chat"

    @property
    def ai_defense_timeout_seconds(self) -> float:
        return self.ai_defense_timeout_ms / 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
