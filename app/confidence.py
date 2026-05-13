"""Confidence scoring + action routing.

Composite score in [0, 1], weighted blend of three signals:

    1. model_self_confidence  (weight 0.5)  -- from Claude's JSON output
    2. query_type_prior       (weight 0.3)  -- how safe is auto-replying for
                                               this type of question
    3. uncertainty_penalty    (weight 0.2)  -- 1.0 minus 0.25 per Claude
                                               uncertainty flag, floored at 0

Final hard rule: complaints are never auto-sent. We cap their final score
at 0.55 so the action is always agent_review or escalate.

Action thresholds:
    > 0.85           -> auto_send
    0.60 - 0.85      -> agent_review
    < 0.60           -> escalate
    complaint        -> at most agent_review, but in practice routed to
                       escalate because the cap keeps the score < 0.60 once
                       any uncertainty flag fires.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import Action, QueryType

WEIGHT_MODEL = 0.5
WEIGHT_PRIOR = 0.3
WEIGHT_PENALTY = 0.2

UNCERTAINTY_STEP = 0.25

COMPLAINT_CAP = 0.55

THRESHOLD_AUTO = 0.85
THRESHOLD_REVIEW = 0.60

QUERY_TYPE_PRIORS: dict[QueryType, float] = {
    "general_enquiry": 0.9,
    "post_sales_checkin": 0.9,
    "pre_sales_pricing": 0.85,
    "pre_sales_availability": 0.8,
    "special_request": 0.6,
    "complaint": 0.2,
}


@dataclass
class ConfidenceBreakdown:
    model_self_confidence: float
    query_type_prior: float
    uncertainty_penalty: float
    raw_score: float
    final_score: float
    complaint_capped: bool


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_confidence(
    *,
    query_type: QueryType,
    model_self_confidence: float,
    uncertainty_flags: list[str],
) -> ConfidenceBreakdown:
    prior = QUERY_TYPE_PRIORS.get(query_type, 0.5)
    penalty = _clamp(1.0 - UNCERTAINTY_STEP * len(uncertainty_flags))
    msc = _clamp(model_self_confidence)

    raw = (
        WEIGHT_MODEL * msc
        + WEIGHT_PRIOR * prior
        + WEIGHT_PENALTY * penalty
    )

    final = _clamp(raw)
    capped = False
    if query_type == "complaint" and final > COMPLAINT_CAP:
        final = COMPLAINT_CAP
        capped = True

    return ConfidenceBreakdown(
        model_self_confidence=msc,
        query_type_prior=prior,
        uncertainty_penalty=penalty,
        raw_score=round(raw, 4),
        final_score=round(final, 2),
        complaint_capped=capped,
    )


def route_action(*, final_score: float, query_type: QueryType) -> Action:
    if query_type == "complaint":
        return "escalate"
    if final_score > THRESHOLD_AUTO:
        return "auto_send"
    if final_score >= THRESHOLD_REVIEW:
        return "agent_review"
    return "escalate"
