"""Hardcoded Villa B1 context.

In a production system this would be read from the `properties` table —
see schema.sql. For the assessment it lives inline so the webhook is
self-contained.
"""

from __future__ import annotations

VILLA_B1 = {
    "property_id": "VILLA_B1",
    "name": "Villa B1",
    "location": "North Goa, India",
    "bedrooms": 4,
    "max_guests": 8,
    "base_rate_inr": 25000,
    "weekend_rate_inr": 32000,
    "currency": "INR",
    "check_in_time": "15:00",
    "check_out_time": "11:00",
    "amenities": [
        "Private swimming pool",
        "Air-conditioned bedrooms",
        "High-speed Wi-Fi",
        "Fully-equipped kitchen",
        "On-call caretaker",
        "Daily housekeeping",
        "Complimentary breakfast for up to 8 guests",
    ],
    "house_rules": [
        "No loud music after 10pm (local noise regulations)",
        "Pets allowed on request",
        "Smoking permitted in outdoor areas only",
    ],
    "caretaker_contact": "+91-9000000000",
    "nearest_airport": "Goa International Airport (GOI), ~45 minutes by car",
    "cancellation_policy": (
        "Full refund up to 14 days before check-in; 50% refund up to 7 days "
        "before; non-refundable thereafter."
    ),
}


def format_for_prompt(property_id: str = "VILLA_B1") -> str:
    """Return a clean text block describing the property, for prompt injection."""
    p = VILLA_B1  # only one property in scope for the assessment

    amenities = "\n".join(f"  - {a}" for a in p["amenities"])
    rules = "\n".join(f"  - {r}" for r in p["house_rules"])

    return (
        f"PROPERTY: {p['name']} ({p['property_id']})\n"
        f"Location: {p['location']}\n"
        f"Bedrooms: {p['bedrooms']} | Max guests: {p['max_guests']}\n"
        f"Base rate: ₹{p['base_rate_inr']:,} / night "
        f"(weekend ₹{p['weekend_rate_inr']:,} / night)\n"
        f"Check-in: {p['check_in_time']} | Check-out: {p['check_out_time']}\n"
        f"Amenities:\n{amenities}\n"
        f"House rules:\n{rules}\n"
        f"Caretaker on call: {p['caretaker_contact']}\n"
        f"Nearest airport: {p['nearest_airport']}\n"
        f"Cancellation policy: {p['cancellation_policy']}"
    )
