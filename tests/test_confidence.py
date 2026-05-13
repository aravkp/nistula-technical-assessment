import pytest

from app.confidence import (
    COMPLAINT_CAP,
    compute_confidence,
    route_action,
)


def test_known_blend_high_confidence_post_sales():
    # msc=1.0, prior(post_sales_checkin)=0.9, penalty=1.0
    # raw = 0.5*1.0 + 0.3*0.9 + 0.2*1.0 = 0.97
    res = compute_confidence(
        query_type="post_sales_checkin",
        model_self_confidence=1.0,
        uncertainty_flags=[],
    )
    assert res.final_score == 0.97
    assert route_action(final_score=res.final_score, query_type="post_sales_checkin") == "auto_send"


def test_known_blend_with_one_uncertainty_flag():
    # msc=0.8, prior(pre_sales_pricing)=0.85, penalty=0.75 (one flag)
    # raw = 0.4 + 0.255 + 0.15 = 0.805 -> 0.81 (rounded)
    res = compute_confidence(
        query_type="pre_sales_pricing",
        model_self_confidence=0.8,
        uncertainty_flags=["dates_unclear"],
    )
    assert res.final_score == pytest.approx(0.81, abs=0.01)
    assert route_action(final_score=res.final_score, query_type="pre_sales_pricing") == "agent_review"


def test_known_blend_special_request_lands_in_review():
    # msc=0.9, prior(special_request)=0.6, penalty=1.0
    # raw = 0.45 + 0.18 + 0.2 = 0.83 -> agent_review
    res = compute_confidence(
        query_type="special_request",
        model_self_confidence=0.9,
        uncertainty_flags=[],
    )
    assert res.final_score == 0.83
    assert route_action(final_score=res.final_score, query_type="special_request") == "agent_review"


def test_complaint_is_capped_at_055_even_with_high_inputs():
    res = compute_confidence(
        query_type="complaint",
        model_self_confidence=1.0,
        uncertainty_flags=[],
    )
    # raw = 0.5 + 0.06 + 0.2 = 0.76, but complaint cap kicks in
    assert res.complaint_capped is True
    assert res.final_score == COMPLAINT_CAP
    assert route_action(final_score=res.final_score, query_type="complaint") == "escalate"


def test_complaint_always_routes_to_escalate_even_in_review_band():
    # Even if a complaint somehow scored in the agent_review band, the
    # router must still escalate it.
    assert route_action(final_score=0.7, query_type="complaint") == "escalate"


def test_uncertainty_penalty_floors_at_zero():
    # 5 flags -> 1.0 - 5*0.25 = -0.25 -> floored to 0.0
    res = compute_confidence(
        query_type="general_enquiry",
        model_self_confidence=0.5,
        uncertainty_flags=["a", "b", "c", "d", "e"],
    )
    assert res.uncertainty_penalty == 0.0
    # raw = 0.25 + 0.27 + 0.0 = 0.52 -> escalate
    assert res.final_score == 0.52
    assert route_action(final_score=res.final_score, query_type="general_enquiry") == "escalate"


def test_clamps_msc_above_one():
    # malformed input from Claude — confidence > 1
    res = compute_confidence(
        query_type="general_enquiry",
        model_self_confidence=1.5,
        uncertainty_flags=[],
    )
    # msc clamps to 1.0, so raw = 0.5 + 0.27 + 0.2 = 0.97
    assert res.model_self_confidence == 1.0
    assert res.final_score == 0.97


def test_clamps_msc_below_zero():
    res = compute_confidence(
        query_type="general_enquiry",
        model_self_confidence=-0.4,
        uncertainty_flags=[],
    )
    assert res.model_self_confidence == 0.0
    # raw = 0 + 0.27 + 0.2 = 0.47
    assert res.final_score == 0.47


def test_action_thresholds():
    # > 0.85 -> auto_send
    assert route_action(final_score=0.86, query_type="general_enquiry") == "auto_send"
    # boundary at 0.85 — strict ">"
    assert route_action(final_score=0.85, query_type="general_enquiry") == "agent_review"
    # 0.60 - 0.85 -> agent_review
    assert route_action(final_score=0.60, query_type="general_enquiry") == "agent_review"
    # < 0.60 -> escalate
    assert route_action(final_score=0.59, query_type="general_enquiry") == "escalate"
