"""
app/services/llm.py
────────────────────
LLM provider routing — OpenAI, Google Gemini, Anthropic, and On-Prem.
All on-prem calls use the OpenAI-compatible /chat/completions endpoint.
"""

from __future__ import annotations
import logging
import httpx

from app.config import Settings
from app.schemas import ChatMessage

logger = logging.getLogger(__name__)

# ── Provider endpoint helpers ─────────────────────────────────────────────────

def _openai_url(settings: Settings) -> str:
    return "https://api.openai.com/v1/chat/completions"


def _custom_url(settings: Settings) -> str:
    ep = settings.llm_model   # Not used directly; custom endpoint comes from request
    # For the backend, custom/onprem uses settings.onprem_base_url
    return settings.onprem_base_url.rstrip("/") + "/chat/completions"


def _google_url(model: str, api_key: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )


def _anthropic_url() -> str:
    return "https://api.anthropic.com/v1/messages"


# ── Main call function ────────────────────────────────────────────────────────

async def call_llm(
    messages: list[ChatMessage],
    settings: Settings,
    model_override: str | None = None,
    provider_override: str | None = None,
    api_key_override: str | None = None,
    base_url_override: str | None = None,
    max_tokens_override: int | None = None,
    temperature_override: float | None = None,
) -> tuple[str, dict]:
    """
    Call the configured LLM and return (response_text, usage_dict).

    Overrides allow the API endpoint to use request-level parameters
    (e.g. when Cisco AI Defense sends its own model name in the body).
    """
    provider = provider_override or settings.llm_provider
    model    = model_override    or settings.llm_model
    api_key  = api_key_override  or settings.llm_api_key
    max_tok  = max_tokens_override  or settings.llm_max_tokens
    temp     = temperature_override if temperature_override is not None else settings.llm_temperature

    # Detect on-prem provider
    if provider == "onprem":
        return await _call_onprem(messages, settings, model, max_tok, temp)

    if provider == "openai":
        return await _call_openai(messages, model, api_key, max_tok, temp)

    if provider == "google":
        return await _call_google(messages, model, api_key, max_tok, temp)

    if provider == "anthropic":
        return await _call_anthropic(messages, model, api_key, max_tok, temp)

    if provider == "custom":
        base_url = base_url_override or settings.onprem_base_url
        return await _call_openai_compatible(
            messages, model, api_key, max_tok, temp,
            base_url=base_url.rstrip("/") + "/chat/completions",
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


async def _call_openai(
    messages: list[ChatMessage],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    url = "https://api.openai.com/v1/chat/completions"
    return await _call_openai_compatible(messages, model, api_key, max_tokens, temperature, url)


async def _call_onprem(
    messages: list[ChatMessage],
    settings: Settings,
    model: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    """Call on-prem OpenAI-compatible server."""
    url = settings.onprem_base_url.rstrip("/") + "/chat/completions"
    api_key = settings.onprem_api_key or "no-key"
    actual_model = model or settings.onprem_model_name
    return await _call_openai_compatible(messages, actual_model, api_key, max_tokens, temperature, url)


async def _call_openai_compatible(
    messages: list[ChatMessage],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
    base_url: str,
) -> tuple[str, dict]:
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    logger.debug("LLM call → %s | model=%s", base_url, model)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(base_url, json=payload, headers=headers)

    if not resp.is_success:
        try:
            err = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"LLM error {resp.status_code}: {str(err)[:300]}")

    data = resp.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "(empty)")
    usage = data.get("usage", {})
    return text, usage


async def _call_google(
    messages: list[ChatMessage],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    # Flatten messages to a single user prompt for Gemini
    prompt = "\n\n".join(
        f"[{m.role.upper()}]: {m.content}"
        for m in messages if m.role != "system"
    )
    system_parts = [m.content for m in messages if m.role == "system"]
    full = ("\n\n".join(system_parts) + "\n\n" + prompt).strip() if system_parts else prompt

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": full}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})

    if not resp.is_success:
        try:
            err = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"Gemini error {resp.status_code}: {str(err)[:300]}")

    data = resp.json()
    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "(empty)")
    return text, {}


async def _call_anthropic(
    messages: list[ChatMessage],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    system = next((m.content for m in messages if m.role == "system"), None)
    chat_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    payload: dict = {"model": model, "max_tokens": max_tokens, "messages": chat_msgs}
    if system:
        payload["system"] = system

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)

    if not resp.is_success:
        try:
            err = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"Anthropic error {resp.status_code}: {str(err)[:300]}")

    data = resp.json()
    text = data.get("content", [{}])[0].get("text", "(empty)")
    usage = data.get("usage", {})
    return text, usage
