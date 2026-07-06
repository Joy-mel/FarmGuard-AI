"""
FarmGuard AI - WhatsApp Bot Interface
========================================
Standalone handler logic for the Twilio WhatsApp webhook, kept separate
from the API layer so the messaging logic (commands, reply formatting)
can be tested, reused, or swapped to a different provider (e.g. Meta's
WhatsApp Cloud API directly) without touching api/main.py.

api/main.py imports from this module and only handles the HTTP plumbing
(receiving the POST, verifying the Twilio signature, returning TwiML).
"""

import os
import sys
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "api"))
from model_pipeline import predict_for_farmer  # noqa: E402
from kenya_counties import KENYA_COUNTIES  # noqa: E402

logger = logging.getLogger("farmguard-whatsapp")

ALLOWED_LOCATIONS = tuple(KENYA_COUNTIES.keys())
ALLOWED_CROPS = ("maize", "beans")


def verify_twilio_signature(request_url: str, form_dict: dict, signature: str, auth_token: str) -> bool:
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set - webhook signature check SKIPPED.")
        return True
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(auth_token)
    return validator.validate(request_url, form_dict, signature)


def parse_location_crop(text: str):
    tokens = [t.lower().strip() for t in text.split() if t.strip()]
    crop = next((t for t in tokens if t in ALLOWED_CROPS), "maize")
    location = next((t for t in tokens if t in ALLOWED_LOCATIONS), "nairobi")
    return location, crop, tokens


def build_status_reply(location: str, crop: str) -> str:
    r = predict_for_farmer(location, crop)
    return (
        f"FarmGuard AI - {r['location'].replace('_', ' ').title()} STATUS\n"
        f"Risk: {r['risk'].upper()}\n"
        f"Soil moisture: {r['soil_moisture_pct']}%  |  NDVI: {r['ndvi']} ({r['vegetation_health']})\n"
        f"Soil type: {r['soil_type']}\n"
        f"{crop.title()} price: KES {r['current_price_kes_per_kg']}/kg "
        f"(forecast KES {r['forecast_price_kes_per_kg']}/kg)"
    )


def build_alerts_reply(location: str, crop: str) -> str:
    r = predict_for_farmer(location, crop)
    if r["risk"] == "normal":
        return f"No high-priority alerts for {r['location'].replace('_', ' ').title()} right now. Conditions are normal."
    lines = [f"ALERT - {r['location'].replace('_', ' ').title()}: {r['risk'].upper()}"]
    lines += [f"- {rec}" for rec in r["recommendations"] if rec][:4]
    return "\n".join(lines)


def build_help_reply() -> str:
    sample_counties = ", ".join(list(ALLOWED_LOCATIONS)[:8]) + ", ... (47 total)"
    return (
        "Welcome to FarmGuard AI!\n"
        "Commands:\n"
        "  status <county> <crop> - current conditions & prices\n"
        "  alerts <county> <crop> - high-priority risk alerts only\n"
        f"Counties: {sample_counties}\n"
        f"Crops: {', '.join(ALLOWED_CROPS)}\n\n"
        "Example: \"status kisumu maize\""
    )


def handle_incoming_message(body: str) -> str:
    """Pure function: WhatsApp message text in, reply text out.
    No I/O, no Twilio objects - easy to unit test directly."""
    text = (body or "").strip().lower()[:200]
    if not text:
        return build_help_reply()

    location, crop, tokens = parse_location_crop(text)

    if "help" in tokens or "hi" in tokens or "menu" in tokens or "start" in tokens:
        return build_help_reply()
    if "alert" in text:
        return build_alerts_reply(location, crop)
    # "status", or any message containing a recognizable county/crop, defaults to status
    return build_status_reply(location, crop)
