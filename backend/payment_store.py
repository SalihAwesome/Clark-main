"""
Payment Card store — an OPTIONAL saved payment card the agent can reuse to auto-fill
checkout / fee-payment forms in future agentic tasks (e.g. paying a traffic fine).

Mirrors profile_store ("My Info"): everything is optional, stored locally in a single
JSON file under the agent workspace. This is a LOCAL, single-user app — the card never
leaves the machine, is never sent to the AI model, and is never logged. It is only read
back to fill a real payment form when the user explicitly runs a task that needs it.

Security note: card data is stored in plain text in agent_workspace/payment.json. Only
use this on your own device. (No external storage, no telemetry.)
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
from typing import Any

WORKSPACE = pathlib.Path(os.getenv("AGENT_WORKSPACE", "agent_workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)
PAYMENT_PATH = WORKSPACE / "payment.json"

_LOCK = threading.Lock()

# Ordered field set shown in the "Payment Card" panel. All optional.
#   key    : stable storage key
#   label  : human label in the UI
#   type   : input hint (text | tel | password) — secret=True fields are masked in the UI
#   secret : whether the UI masks it (card number / CVV)
PAYMENT_FIELDS: list[dict[str, Any]] = [
    {"key": "card_type", "label": "Card Type", "type": "text", "placeholder": "Debit Card or Credit Card"},
    {"key": "cardholder_name", "label": "Cardholder Name", "type": "text"},
    {"key": "card_number", "label": "Card Number", "type": "tel", "secret": True, "placeholder": "•••• •••• •••• ••••"},
    {"key": "expiry", "label": "Expiry (MM/YY)", "type": "text", "placeholder": "MM/YY"},
    {"key": "cvv", "label": "CVV", "type": "password", "secret": True, "placeholder": "•••"},
    {"key": "billing_zip", "label": "Billing Postal Code", "type": "text"},
]


def card_type_label() -> str:
    """Return the card-type label to pick in the payment dialog ('Credit Card' / 'Debit Card'),
    based on the user's saved card. Defaults to 'Debit Card' when unset."""
    saved = load_payment().get("card_type", "").lower()
    return "Credit Card" if "credit" in saved else "Debit Card"

_ALLOWED_KEYS = {f["key"] for f in PAYMENT_FIELDS}


def field_meta() -> list[dict[str, Any]]:
    """The field definitions for the UI (labels, types, which are secret)."""
    return [dict(f) for f in PAYMENT_FIELDS]


def load_payment() -> dict[str, str]:
    """Return the saved card (empty dict if none / unreadable)."""
    with _LOCK:
        if not PAYMENT_PATH.is_file():
            return {}
        try:
            data = json.loads(PAYMENT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(v).strip() for k, v in data.items() if k in _ALLOWED_KEYS and str(v).strip()}


def save_payment(values: dict[str, Any]) -> dict[str, str]:
    """Replace the saved card with `values` (only known, non-empty keys are kept)."""
    clean = {k: str(v).strip() for k, v in (values or {}).items()
             if k in _ALLOWED_KEYS and str(v).strip()}
    with _LOCK:
        PAYMENT_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean
