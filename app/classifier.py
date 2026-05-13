"""Rule-based query classifier.

Priority order (first match wins):
    1. complaint                  -- always checked first; trumps everything else
    2. pre_sales_availability     -- date ranges, "available", "free", etc.
    3. pre_sales_pricing          -- "rate", "price", "per night", currency markers
    4. special_request            -- "early check-in", "late checkout", "airport", "chef"
    5. post_sales_checkin         -- "check-in", "wifi", "arrive", "key", "caretaker"
    6. general_enquiry            -- fallback

The priority is intentional in two places.

Complaints come first because they frequently mention pricing ("I want
a refund") or availability ("we leave tomorrow"); without the
complaint-first ordering they would be misrouted into auto-send.

Special-request comes before post-sales-checkin because "early
check-in" and "late checkout" are textually a superset of "check-in"
and "checkout" — a literal-order match on "check-in" would steal those
messages from the operational queue that actually needs to action
them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas import QueryType

CLASSIFIER_VERSION = "rules-v1"

# Compiled once at import time.
_COMPLAINT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bnot working\b",
        r"\bdoesn'?t work\b",
        r"\bbroken\b",
        r"\bunacceptable\b",
        r"\brefund\b",
        r"\bdisappointed\b",
        r"\bterrible\b",
        r"\bhorrible\b",
        r"\bawful\b",
        r"\bfilthy\b",
        r"\bdirty\b",
        r"\bleaking\b",
        r"\bleaks?\b",
        r"\bno hot water\b",
        r"\bcold water\b",
        r"\bac\s*(is(n'?t)?|isn'?t|not)\b",
        r"\bcomplaint\b",
        r"\bworst\b",
        r"\bnever (again|coming|stay)\b",
        # strong negation + amenity word
        r"\b(no|not|never)\b.{0,20}\b(wifi|water|ac|aircon|power|electricity|breakfast)\b",
    ]
]

_AVAILABILITY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bavailab(le|ility)\b",
        r"\bfree\b",
        r"\bvacan(t|cy|cies)\b",
        r"\bopen\b",
        r"\bbook(ing)?\b.{0,20}\b(for|from|on|between)\b",
        r"\bfrom\s+\w+\s+to\s+\w+\b",
        r"\bbetween\s+\w+\s+and\s+\w+\b",
        r"\b\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}",
        r"\bdates?\b",
    ]
]

_PRICING_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\brates?\b",
        r"\bpric(e|ing|es)\b",
        r"\bcosts?\b",
        r"\bper\s+night\b",
        r"\bnightly\b",
        r"\bhow much\b",
        r"\bquote\b",
        r"\btariff\b",
        r"\bcharges?\b",
        r"₹",
        r"\b(inr|rs\.?|rupees?)\b",
    ]
]

_CHECKIN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bcheck[\s\-]?in\b",
        r"\bwi[\s\-]?fi\b",
        r"\bpassword\b",
        r"\barriv(e|ing|al)\b",
        r"\bkeys?\b",
        r"\bcaretaker\b",
        r"\bdirections?\b",
        r"\baddress\b",
        r"\bhow do (i|we) get\b",
        r"\bgate\s*code\b",
    ]
]

_SPECIAL_REQUEST_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bearly check[\s\-]?in\b",
        r"\blate check[\s\-]?out\b",
        r"\bairport\b",
        r"\btransfer\b",
        r"\bpick[\s\-]?up\b",
        r"\bchef\b",
        r"\bextra bed\b",
        r"\bcot\b",
        r"\bcan you arrange\b",
        r"\bcould you organise\b",
        r"\bcould you organize\b",
        r"\bplease arrange\b",
        r"\bspecial request\b",
    ]
]


@dataclass
class ClassifierResult:
    query_type: QueryType
    matched_keywords: list[str]


def _matches(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
        m = pat.search(text)
        if m:
            found.append(m.group(0).lower())
    return found


def classify(message: str) -> ClassifierResult:
    """Classify a guest message into one of six query types.

    Returns the label plus the list of matched keyword spans (handy for
    debugging and for the confidence layer).
    """
    text = message or ""

    complaint_hits = _matches(text, _COMPLAINT_PATTERNS)
    if complaint_hits:
        return ClassifierResult("complaint", complaint_hits)

    availability_hits = _matches(text, _AVAILABILITY_PATTERNS)
    if availability_hits:
        return ClassifierResult("pre_sales_availability", availability_hits)

    pricing_hits = _matches(text, _PRICING_PATTERNS)
    if pricing_hits:
        return ClassifierResult("pre_sales_pricing", pricing_hits)

    # Special-request must come before check-in so that "early check-in"
    # and "late checkout" don't get stolen by the generic check-in rule.
    special_hits = _matches(text, _SPECIAL_REQUEST_PATTERNS)
    if special_hits:
        return ClassifierResult("special_request", special_hits)

    checkin_hits = _matches(text, _CHECKIN_PATTERNS)
    if checkin_hits:
        return ClassifierResult("post_sales_checkin", checkin_hits)

    return ClassifierResult("general_enquiry", [])
