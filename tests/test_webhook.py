from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_claude_client
from app.schemas import ClaudeDraft


class StubClaude:
    """Drop-in replacement for ClaudeClient in tests.

    `result` is the ClaudeDraft to return. If `raise_exc` is set, the stub
    raises it instead — but in practice the real ClaudeClient swallows
    errors and returns a degraded draft, so to simulate "API failure" we
    just hand back a degraded ClaudeDraft directly.
    """

    def __init__(self, result: ClaudeDraft):
        self.result = result
        self.calls: list[dict] = []

    def draft_reply(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _client(stub: StubClaude) -> TestClient:
    app.dependency_overrides[get_claude_client] = lambda: stub
    return TestClient(app)


def _payload(message: str, source: str = "whatsapp") -> dict:
    return {
        "source": source,
        "guest_name": "Aarav Kapoor",
        "message": message,
        "timestamp": "2026-06-12T09:30:00+05:30",
        "booking_ref": "NIS-2026-0142",
        "property_id": "VILLA_B1",
    }


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_happy_path_pricing_returns_high_confidence():
    stub = StubClaude(
        ClaudeDraft(
            reply="Our base rate for Villa B1 is ₹18,000 per night (up to 4 guests).",
            self_confidence=0.95,
            uncertainty_flags=[],
        )
    )
    client = _client(stub)

    resp = client.post(
        "/webhook/message",
        json=_payload("What is the per night rate for 4 guests?"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_type"] == "pre_sales_pricing"
    assert body["drafted_reply"].startswith("Our base rate")
    # msc=0.95, prior=0.85, penalty=1.0 -> 0.475 + 0.255 + 0.2 = 0.93
    assert body["confidence_score"] == pytest.approx(0.93, abs=0.01)
    assert body["action"] == "auto_send"
    # message_id is a UUID string
    assert len(body["message_id"]) == 36


def test_complaint_routes_to_escalate_regardless_of_msc():
    stub = StubClaude(
        ClaudeDraft(
            reply="I'm so sorry to hear about this — our caretaker is on his way now.",
            self_confidence=0.95,
            uncertainty_flags=[],
        )
    )
    client = _client(stub)

    resp = client.post(
        "/webhook/message",
        json=_payload("The AC is broken in the master bedroom, this is unacceptable!"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_type"] == "complaint"
    assert body["action"] == "escalate"
    assert body["confidence_score"] <= 0.55


def test_claude_failure_returns_degraded_response_with_200():
    # Simulates the real client's behaviour on any failure.
    stub = StubClaude(
        ClaudeDraft(
            reply="Thank you for your message — our team will get back to you shortly.",
            self_confidence=0.0,
            uncertainty_flags=["api_error"],
        )
    )
    client = _client(stub)

    resp = client.post(
        "/webhook/message",
        json=_payload("Can we get an early check-in at 11am?"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["drafted_reply"].startswith("Thank you for your message")
    # msc=0.0, prior(special_request)=0.6, penalty=0.75 (1 flag)
    # raw = 0 + 0.18 + 0.15 = 0.33 -> escalate
    assert body["action"] == "escalate"


def test_malformed_payload_returns_422():
    client = TestClient(app)
    bad = {
        "source": "unknown_channel",  # not in the Literal
        "guest_name": "X",
        "message": "hi",
        "timestamp": "not a date",
        "booking_ref": "X",
        "property_id": "X",
    }
    resp = client.post("/webhook/message", json=bad)
    assert resp.status_code == 422


def test_missing_required_field_returns_422():
    client = TestClient(app)
    resp = client.post(
        "/webhook/message",
        json={"source": "whatsapp", "message": "hi"},
    )
    assert resp.status_code == 422


def test_availability_query_passes_through_to_claude_with_right_query_type():
    stub = StubClaude(
        ClaudeDraft(
            reply="Yes, Villa B1 is available 21-25 June. Shall I hold those dates?",
            self_confidence=0.9,
            uncertainty_flags=[],
        )
    )
    client = _client(stub)

    resp = client.post(
        "/webhook/message",
        json=_payload("Is Villa B1 available from 21st June to 25th June?"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_type"] == "pre_sales_availability"
    # The stub recorded the call — check Claude got the right query_type
    assert stub.calls[0]["query_type"] == "pre_sales_availability"
    assert stub.calls[0]["guest_name"] == "Aarav Kapoor"
