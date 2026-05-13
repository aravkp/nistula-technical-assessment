"""Thin wrapper around the Anthropic Python SDK."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from anthropic import Anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    CLAUDE_TIMEOUT_SECONDS,
)
from app.property_context import format_for_prompt
from app.schemas import ClaudeDraft

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are drafting guest-facing replies on behalf of the property team at "
    "Nistula, a luxury villa hospitality brand operating boutique private "
    "villas across India. Your tone is warm, concise and professional — never "
    "overly formal, never effusive. Address guests by their first name when "
    "appropriate. Reply in plain prose, no markdown, no bullet lists unless "
    "the guest explicitly asks for one.\n\n"
    "Hard rules:\n"
    "- Never invent facts that are not present in the property context block.\n"
    "- If a guest asks something you cannot answer from the context, say a "
    "  team member will confirm the detail shortly rather than guessing.\n"
    "- For complaints, acknowledge the issue first and commit to immediate "
    "  action; never promise a refund or a specific resolution on your own.\n"
    "- Keep replies under 120 words unless the guest's question genuinely "
    "  needs more.\n\n"
    "Output format: return ONLY a JSON object — no prose around it — with "
    "exactly these keys:\n"
    '  {"reply": "...", "self_confidence": 0.0-1.0, '
    '"uncertainty_flags": ["..."]}\n\n'
    "self_confidence is your honest estimate (0–1) that the reply is correct "
    "and complete given the context. uncertainty_flags is a list of short "
    "snake_case tokens for anything you had to guess or fudge — e.g. "
    '"dates_unclear", "missing_guest_count", "policy_not_in_context".'
)


def _build_user_content(
    *,
    guest_name: str,
    message_text: str,
    query_type: str,
    property_id: str,
) -> str:
    return (
        f"Guest name: {guest_name}\n"
        f"Query type (rule-based classifier): {query_type}\n"
        f"Property context:\n{format_for_prompt(property_id)}\n\n"
        f'Guest message:\n"""\n{message_text}\n"""\n\n'
        "Draft the reply and return only the JSON object."
    )


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_FIRST_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Pull a JSON object out of Claude's text response.

    Tries (in order):
      1. parse the whole thing as JSON
      2. strip ```json ... ``` fences
      3. grab the first balanced `{...}` block via regex
    Raises ValueError if nothing parses.
    """
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced = _FENCED_JSON.search(raw)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    obj = _FIRST_OBJECT.search(raw)
    if obj:
        return json.loads(obj.group(0))

    raise ValueError("No JSON object found in Claude response")


def _degraded(message_id: str, reason: str) -> ClaudeDraft:
    logger.warning(
        "claude_degraded message_id=%s reason=%s", message_id, reason
    )
    return ClaudeDraft(
        reply=(
            "Thank you for your message — our team will get back to you "
            "shortly."
        ),
        self_confidence=0.0,
        uncertainty_flags=["api_error"],
    )


class ClaudeClient:
    """Drafts replies via the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._model = model or CLAUDE_MODEL
        self._client: Anthropic | None = None

    def _lazy_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(
                api_key=self._api_key,
                timeout=CLAUDE_TIMEOUT_SECONDS,
            )
        return self._client

    def draft_reply(
        self,
        *,
        message_id: str,
        guest_name: str,
        message_text: str,
        query_type: str,
        property_id: str,
    ) -> ClaudeDraft:
        if not self._api_key:
            return _degraded(message_id, "missing_api_key")

        user_content = _build_user_content(
            guest_name=guest_name,
            message_text=message_text,
            query_type=query_type,
            property_id=property_id,
        )

        try:
            response = self._lazy_client().messages.create(
                model=self._model,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:  # noqa: BLE001 — degrade on any SDK/network error
            logger.exception(
                "claude_api_error message_id=%s error=%s",
                message_id,
                exc.__class__.__name__,
            )
            return _degraded(message_id, f"api_error:{exc.__class__.__name__}")

        # Concatenate all text blocks in the response.
        raw = "".join(
            getattr(block, "text", "") for block in response.content
        ).strip()

        try:
            payload = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.exception(
                "claude_parse_error message_id=%s error=%s raw_head=%r",
                message_id,
                exc.__class__.__name__,
                raw[:200],
            )
            return _degraded(message_id, "parse_error")

        try:
            return ClaudeDraft(
                reply=str(payload.get("reply", "")).strip(),
                self_confidence=float(payload.get("self_confidence", 0.0)),
                uncertainty_flags=list(payload.get("uncertainty_flags") or []),
            )
        except (TypeError, ValueError) as exc:
            logger.exception(
                "claude_schema_error message_id=%s error=%s",
                message_id,
                exc.__class__.__name__,
            )
            return _degraded(message_id, "schema_error")
