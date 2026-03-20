"""
app/services/defense.py
────────────────────────
Cisco AI Defense Chat Inspection service.
Handles both API-direct and Gateway modes.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx

from app.config import Settings
from app.schemas import (
    DefenseInspectRequest,
    DefenseInspectResponse,
    DefenseMessageItem,
    DefenseMetadata,
    DefenseConfig,
    DefenseEnabledRule,
)

logger = logging.getLogger(__name__)


def _build_headers(settings: Settings, extra_headers: dict | None = None) -> dict:
    """Build request headers for AI Defense call."""
    headers = {"Content-Type": "application/json"}
    if settings.ai_defense_mode == "api" and settings.ai_defense_api_key:
        headers["X-Cisco-AI-Defense-API-Key"] = settings.ai_defense_api_key
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _build_inspect_url(settings: Settings) -> str:
    """Resolve the full inspect endpoint URL."""
    if settings.ai_defense_mode == "gateway":
        return settings.ai_defense_base_url.rstrip("/")
    return settings.ai_defense_inspect_url


async def inspect(
    content: str,
    role: str,
    settings: Settings,
    use_server_policy: bool = True,
    enabled_rules: list[str] | None = None,
    transaction_id: str | None = None,
) -> DefenseInspectResponse:
    """
    Send a single message to AI Defense for inspection.

    Args:
        content:           The text to inspect.
        role:              'user' or 'assistant'.
        settings:          App settings.
        use_server_policy: If True, omit config so server-side policy applies.
        enabled_rules:     Custom rule list (used when use_server_policy=False).
        transaction_id:    Optional client transaction ID for tracing.

    Returns:
        DefenseInspectResponse — normalised inspect result.

    Raises:
        httpx.HTTPError on network/HTTP failures.
    """
    url = _build_inspect_url(settings)
    headers = _build_headers(settings)

    payload = DefenseInspectRequest(
        messages=[DefenseMessageItem(role=role, content=content)],
        metadata=DefenseMetadata(
            src_app="velocis-intelli-agent",
            created_at=datetime.now(timezone.utc).isoformat(),
            client_transaction_id=transaction_id or f"txn-{int(datetime.now().timestamp()*1000)}",
        ),
    )

    # Only include config.enabled_rules when NOT using server policy
    if not use_server_policy and enabled_rules:
        payload.config = DefenseConfig(
            enabled_rules=[DefenseEnabledRule(rule_name=r) for r in enabled_rules]
        )

    timeout = settings.ai_defense_timeout_seconds

    async with httpx.AsyncClient(timeout=timeout) as client:
        logger.debug("AI Defense inspect → %s | role=%s", url, role)
        resp = await client.post(url, headers=headers, json=payload.model_dump(exclude_none=True))

    if not resp.is_success:
        try:
            err_detail = resp.json().get("message", resp.text)
        except Exception:
            err_detail = resp.text
        raise httpx.HTTPStatusError(
            f"AI Defense {resp.status_code}: {str(err_detail)[:200]}",
            request=resp.request,
            response=resp,
        )

    data = resp.json()

    return DefenseInspectResponse(
        is_safe=data.get("is_safe", True),
        severity=data.get("severity", "NONE_SEVERITY"),
        classifications=data.get("classifications", []),
        rules=data.get("rules", []),
        attack_technique=data.get("attack_technique", ""),
        explanation=data.get("explanation", ""),
        event_id=data.get("event_id", ""),
        action=data.get("action", ""),
    )


def should_block(result: DefenseInspectResponse) -> bool:
    """
    Determine whether the response warrants blocking the request.
    Logic mirrors the frontend's shouldBlock() function.
    """
    if result.is_safe is True:
        return False
    if result.is_safe is False:
        # Also respect explicit action field
        if result.action and result.action.lower() != "block":
            return False
        return True
    return False
