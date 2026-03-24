"""
app/schemas.py
──────────────
All Pydantic request/response schemas.

Key design: the /v1/chat/completions endpoint accepts BOTH the standard
OpenAI request body AND the shape that Cisco AI Defense attack-validation
portal sends (it wraps messages in the same OpenAI-compatible structure),
so a single schema covers both use cases.
"""

from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, Field
import time
import uuid


# ═══════════════════════════════════════════════════
#  OpenAI-compatible Chat Completions
# ═══════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """
    OpenAI-compatible chat completion request.
    Also accepts the body shape sent by Cisco AI Defense attack-validation.

    AI Defense sends:
      { "model": "...", "messages": [...], "stream": false, ... }
    which is identical to the OpenAI format — so one schema handles both.
    """
    model: Optional[str] = None
    messages: list[ChatMessage]
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = 1
    stop: Optional[Union[str, list[str]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None
    # Extra fields some clients/AI Defense portal may include — allow passthrough
    metadata: Optional[dict[str, Any]] = None

    class Config:
        extra = "allow"   # Accept unknown fields without raising validation errors


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """Standard OpenAI chat completion response."""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


# ═══════════════════════════════════════════════════
#  Cisco AI Defense — Chat Inspection API
# ═══════════════════════════════════════════════════

class DefenseMessageItem(BaseModel):
    role: str
    content: str


class DefenseEnabledRule(BaseModel):
    rule_name: str


class DefenseConfig(BaseModel):
    enabled_rules: Optional[list[DefenseEnabledRule]] = None


class DefenseMetadata(BaseModel):
    src_app: str = "velocis-intelli-agent"
    created_at: Optional[str] = None
    client_transaction_id: Optional[str] = None


class DefenseInspectRequest(BaseModel):
    """ChatInspectRequest sent to /api/v1/inspect/chat"""
    messages: list[DefenseMessageItem]
    metadata: Optional[DefenseMetadata] = None
    config: Optional[DefenseConfig] = None


class DefenseClassification(BaseModel):
    category: Optional[str] = None
    rule_name: Optional[str] = None
    severity: Optional[str] = None
    entity_types: Optional[list[str]] = None

    class Config:
        extra = "allow"


class DefenseInspectResponse(BaseModel):
    """InspectResponse returned by AI Defense."""
    is_safe: bool = True
    severity: str = "NONE_SEVERITY"
    classifications: list[Any] = []
    rules: list[Any] = []
    attack_technique: str = ""
    explanation: str = ""
    event_id: str = ""
    action: str = ""

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════
#  Config API (for frontend to fetch env-based config)
# ═══════════════════════════════════════════════════

class OnPremConfig(BaseModel):
    model_name: str
    base_url: str
    has_api_key: bool


class AppConfig(BaseModel):
    """Sent to the frontend so it knows the on-prem model details."""
    onprem: OnPremConfig
    ai_defense_mode: str
    ai_defense_configured: bool
    gateway_model: str  # model name to use when AI Defense gateway mode is active


# ═══════════════════════════════════════════════════
#  Error Response
# ═══════════════════════════════════════════════════

class ErrorDetail(BaseModel):
    message: str
    type: str = "api_error"
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
