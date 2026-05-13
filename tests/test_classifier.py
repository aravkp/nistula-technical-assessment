import pytest

from app.classifier import classify


@pytest.mark.parametrize(
    "message",
    [
        "Hi, is Villa B1 available from 21st June to 25th June?",
        "Are the dates between Dec 12 and Dec 18 free?",
        "Looking for vacancy next weekend",
    ],
)
def test_classifies_availability(message):
    assert classify(message).query_type == "pre_sales_availability"


@pytest.mark.parametrize(
    "message",
    [
        "What is the per night rate for 4 guests?",
        "How much does it cost in INR for a weekday stay?",
    ],
)
def test_classifies_pricing(message):
    assert classify(message).query_type == "pre_sales_pricing"


@pytest.mark.parametrize(
    "message",
    [
        "Hi, what is the wifi password?",
        "We are arriving at 3pm, where do we collect the keys?",
        "Can you share the check-in instructions and caretaker number?",
    ],
)
def test_classifies_checkin(message):
    assert classify(message).query_type == "post_sales_checkin"


@pytest.mark.parametrize(
    "message",
    [
        "Could you arrange an airport pickup from Goa?",
        "We'd love a private chef for dinner on Saturday",
        "Can we get an early check-in at 11am?",
    ],
)
def test_classifies_special_request(message):
    assert classify(message).query_type == "special_request"


@pytest.mark.parametrize(
    "message",
    [
        "The AC isn't working in the master bedroom, this is unacceptable",
        "There is no hot water and the bathroom is filthy",
        "We want a refund, the experience has been terrible",
    ],
)
def test_classifies_complaint(message):
    assert classify(message).query_type == "complaint"


def test_complaint_beats_pricing_when_both_present():
    msg = "Your rate of 25000 per night is unacceptable, we want a refund"
    assert classify(msg).query_type == "complaint"


def test_complaint_beats_availability_when_both_present():
    msg = "The AC is broken — are you even available to fix it tomorrow?"
    assert classify(msg).query_type == "complaint"


def test_special_request_beats_checkin_when_both_present():
    # "early check-in" must route to special_request, not post_sales_checkin
    msg = "Could you arrange an early check-in at 11am please?"
    assert classify(msg).query_type == "special_request"


def test_general_enquiry_fallback():
    msg = "Hi, I came across your property on Instagram and wanted to say hello."
    assert classify(msg).query_type == "general_enquiry"


def test_classifier_returns_matched_keywords():
    res = classify("The AC is broken and there is no hot water")
    assert res.query_type == "complaint"
    assert res.matched_keywords  # non-empty list
