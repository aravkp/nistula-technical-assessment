"""FastAPI app + /webhook/message route."""

from __future__ import annotations

import logging
import uuid

from fastapi import Depends, FastAPI

from app.claude_client import ClaudeClient
from app.classifier import classify
from app.config import configure_logging
from app.confidence import compute_confidence, route_action
from app.schemas import InboundMessage, WebhookResponse

configure_logging()
logger = logging.getLogger("nistula.webhook")

app = FastAPI(title="Nistula Guest Messaging Webhook", version="1.0.0")

# Single instance per process — the SDK client is cheap to instantiate but
# we still want connection pooling across requests.
_default_client = ClaudeClient()


def get_claude_client() -> ClaudeClient:
    """Dependency injector so tests can override with a stub client."""
    return _default_client


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/message", response_model=WebhookResponse)
def webhook_message(
    payload: InboundMessage,
    claude: ClaudeClient = Depends(get_claude_client),
) -> WebhookResponse:
    message_id = str(uuid.uuid4())

    classifier_result = classify(payload.message)
    query_type = classifier_result.query_type

    logger.info(
        "inbound message_id=%s source=%s query_type=%s booking_ref=%s keywords=%s",
        message_id,
        payload.source,
        query_type,
        payload.booking_ref,
        classifier_result.matched_keywords,
    )

    draft = claude.draft_reply(
        message_id=message_id,
        guest_name=payload.guest_name,
        message_text=payload.message,
        query_type=query_type,
        property_id=payload.property_id,
    )

    breakdown = compute_confidence(
        query_type=query_type,
        model_self_confidence=draft.self_confidence,
        uncertainty_flags=draft.uncertainty_flags,
    )
    action = route_action(final_score=breakdown.final_score, query_type=query_type)

    logger.info(
        "outbound message_id=%s query_type=%s confidence=%s action=%s "
        "model_msc=%s prior=%s penalty=%s capped=%s flags=%s",
        message_id,
        query_type,
        breakdown.final_score,
        action,
        breakdown.model_self_confidence,
        breakdown.query_type_prior,
        breakdown.uncertainty_penalty,
        breakdown.complaint_capped,
        draft.uncertainty_flags,
    )

    return WebhookResponse(
        message_id=message_id,
        query_type=query_type,
        drafted_reply=draft.reply,
        confidence_score=breakdown.final_score,
        action=action,
    )
