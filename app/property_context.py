"""Hardcoded Villa B1 context.

In a production system this would be read from the `properties` table —
see schema.sql. For the assessment it lives inline so the webhook is
self-contained.
"""

from __future__ import annotations

VILLA_B1 = {
    "property_id": "VILLA_B1",
    "name": "Villa B1",
    "location": "Assagao, North Goa",
    "bedrooms": 3,
    "max_guests": 6,
    "private_pool": True,
    "check_in_time": "14:00",
    "check_out_time": "11:00",
    "base_rate_inr": 18000,           # covers up to 4 guests
    "extra_guest_rate_inr": 2000,     # per night, per person beyond 4
    "wifi_password": "Nistula@2024",
    "caretaker": "Available 8am to 10pm",
    "chef_on_call": True,             # pre-booking required
    "availability_april_20_24": "Available",
    "cancellation_policy": "Free cancellation up to 7 days before check-in.",
}


def format_for_prompt(property_id: str = "VILLA_B1") -> str:
    """Return a clean text block describing the property, for prompt injection."""
    p = VILLA_B1  # only one property in scope for the assessment

    pool = "Yes" if p["private_pool"] else "No"
    chef = (
        "Yes (pre-booking required)" if p["chef_on_call"] else "No"
    )

    return (
        f"PROPERTY: {p['name']} ({p['property_id']})\n"
        f"Location: {p['location']}\n"
        f"Bedrooms: {p['bedrooms']} | Max guests: {p['max_guests']}\n"
        f"Private pool: {pool}\n"
        f"Check-in: {p['check_in_time']} (2pm) | "
        f"Check-out: {p['check_out_time']} (11am)\n"
        f"Base rate: ₹{p['base_rate_inr']:,} per night (covers up to 4 guests)\n"
        f"Extra guest rate: ₹{p['extra_guest_rate_inr']:,} per night, "
        f"per person beyond 4\n"
        f"WiFi password: {p['wifi_password']}\n"
        f"Caretaker: {p['caretaker']}\n"
        f"Chef on call: {chef}\n"
        f"Availability 20-24 April: {p['availability_april_20_24']}\n"
        f"Cancellation policy: {p['cancellation_policy']}"
    )
