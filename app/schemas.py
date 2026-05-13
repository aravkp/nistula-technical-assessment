from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["whatsapp", "booking_com", "airbnb", "instagram", "direct"]

QueryType = Literal[
    "pre_sales_availability",
    "pre_sales_pricing",
    "post_sales_checkin",
    "special_request",
    "complaint",
    "general_enquiry",
]

Action = Literal["auto_send", "agent_review", "escalate"]


class InboundMessage(BaseModel):
    source: Source
    guest_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    timestamp: datetime
    booking_ref: str = Field(min_length=1)
    property_id: str = Field(min_length=1)


class NormalisedMessage(BaseModel):
    message_id: str
    source: Source
    guest_name: str
    message_text: str
    timestamp: datetime
    booking_ref: str
    property_id: str
    query_type: QueryType


class ClaudeDraft(BaseModel):
    reply: str
    self_confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_flags: list[str] = Field(default_factory=list)


class WebhookResponse(BaseModel):
    message_id: str
    query_type: QueryType
    drafted_reply: str
    confidence_score: float
    action: Action
