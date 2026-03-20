"""
app/routers/chat.py
────────────────────
POST /v1/chat/completions

Accepts:
  • Standard OpenAI chat completion request (from the frontend)
  • Cisco AI Defense attack-validation request (same shape — just works)

Flow:
  1. Log raw request
  2. AI Defense — inspect user prompt
  3. If blocked → return 200 with block message (OpenAI-compatible body)
  4. Call LLM
  5. AI Defense — inspect LLM response
  6. If blocked → return 200 with block message
  7. Return final response + persist to DB
"""

from __future__ import annotations
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db, ChatSession, ChatMessage as DBMessage, RequestLog
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    Usage,
    ChatMessage,
)
from app.services import defense as defense_svc
from app.services import llm as llm_svc

logger = logging.getLogger(__name__)
router = APIRouter()

BLOCK_FINISH_REASON = "content_filter"

_SYSTEM_DEFAULT = (
    "You are a helpful, accurate, and concise assistant. "
    "Always provide factual and useful responses."
)


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    summary="OpenAI-compatible chat completion with AI Defense guardrails",
    description=(
        "Drop-in replacement for OpenAI /v1/chat/completions. "
        "Requests are inspected by Cisco AI Defense before being forwarded to the LLM. "
        "LLM responses are also inspected before being returned. "
        "Cisco AI Defense attack-validation sends the same payload structure — "
        "so this endpoint works directly as the target for red-team testing."
    ),
)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> ChatCompletionResponse:
    start_ts = time.time()
    req_id = f"chatcmpl-{uuid.uuid4().hex[:20]}"
    client_ip = request.client.host if request.client else "unknown"

    # ── Determine model / provider ────────────────────────────────────────────
    # Priority: body.model → env settings
    req_model = body.model or settings.llm_model
    provider  = settings.llm_provider

    # If the request body specifies the on-prem model name, route to on-prem
    if req_model and (
        req_model == settings.onprem_model_name
        or (settings.onprem_base_url and req_model.startswith("onprem"))
    ):
        provider  = "onprem"
        req_model = settings.onprem_model_name

    # ── Extract messages ──────────────────────────────────────────────────────
    messages: list[ChatMessage] = body.messages  # type: ignore[assignment]

    # Ensure there's a system message
    has_system = any(m.role == "system" for m in messages)
    if not has_system:
        messages = [ChatMessage(role="system", content=_SYSTEM_DEFAULT)] + list(messages)

    # The user-facing content = last user message
    user_content = next(
        (m.content for m in reversed(messages) if m.role == "user"),
        "",
    )

    # ── AI Defense — inspect prompt ───────────────────────────────────────────
    defense_configured = bool(
        settings.ai_defense_api_key or settings.ai_defense_mode == "gateway"
    )
    defense_input_result = None
    defense_output_result = None

    if defense_configured and user_content:
        try:
            txn_id = f"{req_id}-input"
            defense_input_result = await defense_svc.inspect(
                content=user_content,
                role="user",
                settings=settings,
                transaction_id=txn_id,
            )
            logger.info(
                "AI Defense INPUT: is_safe=%s severity=%s",
                defense_input_result.is_safe,
                defense_input_result.severity,
            )
        except Exception as exc:
            logger.warning("AI Defense input scan failed (proceeding): %s", exc)

    # Block if unsafe
    if defense_input_result and defense_svc.should_block(defense_input_result):
        block_msg = (
            "⚠️ This request was blocked by Cisco AI Defense due to a policy violation. "
            "Your query could not be processed."
        )
        resp = _make_response(req_id, req_model, block_msg, BLOCK_FINISH_REASON)
        await _persist_log(
            db, client_ip, body, resp,
            defense_input_result.model_dump(),
            None, start_ts, blocked=True, block_stage="input",
        )
        return resp

    # ── Call LLM ──────────────────────────────────────────────────────────────
    max_tokens  = body.max_tokens  or settings.llm_max_tokens
    temperature = body.temperature if body.temperature is not None else settings.llm_temperature

    try:
        llm_text, usage_raw = await llm_svc.call_llm(
            messages=messages,
            settings=settings,
            model_override=req_model,
            provider_override=provider,
            max_tokens_override=max_tokens,
            temperature_override=temperature,
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        await _persist_log(db, client_ip, body, None, defense_input_result and defense_input_result.model_dump(), None, start_ts, blocked=False, block_stage=None)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    # ── AI Defense — inspect response ─────────────────────────────────────────
    if defense_configured and llm_text:
        try:
            txn_id = f"{req_id}-output"
            defense_output_result = await defense_svc.inspect(
                content=llm_text,
                role="assistant",
                settings=settings,
                transaction_id=txn_id,
            )
            logger.info(
                "AI Defense OUTPUT: is_safe=%s severity=%s",
                defense_output_result.is_safe,
                defense_output_result.severity,
            )
        except Exception as exc:
            logger.warning("AI Defense output scan failed (proceeding): %s", exc)

    if defense_output_result and defense_svc.should_block(defense_output_result):
        block_msg = (
            "⚠️ The AI response was blocked by Cisco AI Defense due to a policy violation."
        )
        resp = _make_response(req_id, req_model, block_msg, BLOCK_FINISH_REASON)
        await _persist_log(
            db, client_ip, body, resp,
            defense_input_result.model_dump() if defense_input_result else None,
            defense_output_result.model_dump(),
            start_ts, blocked=True, block_stage="output",
        )
        return resp

    # ── Build final response ──────────────────────────────────────────────────
    usage = Usage(
        prompt_tokens=usage_raw.get("prompt_tokens", 0),
        completion_tokens=usage_raw.get("completion_tokens", 0),
        total_tokens=usage_raw.get("total_tokens", 0),
    )
    resp = ChatCompletionResponse(
        id=req_id,
        model=req_model,
        choices=[Choice(message=ChoiceMessage(content=llm_text))],
        usage=usage,
    )

    await _persist_log(
        db, client_ip, body, resp,
        defense_input_result.model_dump()  if defense_input_result  else None,
        defense_output_result.model_dump() if defense_output_result else None,
        start_ts, blocked=False, block_stage=None,
    )
    return resp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(req_id: str, model: str, content: str, finish_reason: str) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id=req_id,
        model=model,
        choices=[Choice(message=ChoiceMessage(content=content), finish_reason=finish_reason)],
    )


async def _persist_log(
    db: AsyncSession,
    client_ip: str,
    body: ChatCompletionRequest,
    response: ChatCompletionResponse | None,
    defense_input: dict | None,
    defense_output: dict | None,
    start_ts: float,
    blocked: bool,
    block_stage: str | None,
) -> None:
    try:
        latency_ms = (time.time() - start_ts) * 1000
        log = RequestLog(
            source_ip=client_ip,
            request_body=body.model_dump(exclude_none=True),
            response_body=response.model_dump() if response else None,
            http_status=200,
            defense_input_result=defense_input,
            defense_output_result=defense_output,
            latency_ms=round(latency_ms, 2),
            blocked=blocked,
            block_stage=block_stage,
        )
        db.add(log)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist request log: %s", exc)
