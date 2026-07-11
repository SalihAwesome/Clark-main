"""Local JSON-backed profile store with ID-card image extraction.

The user can save identity fields (name, email, date of birth, etc.) that the
agent uses to auto-fill forms. The profile can also be populated by uploading
a photo of an ID card: the vision model extracts the text and the text model
turns it into structured JSON fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

PROFILE_PATH = Path(__file__).parent / "agent_workspace" / "profile.json"
PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK = Lock()

# ── Field definitions ──────────────────────────────────────────────────────────
#   key       : short snake_case identifier used in the backend and the UI
#   label     : human-readable label shown in the UI
#   type      : input hint for the UI (text | email | tel | date)
#   format    : expected text format for date fields the agent types into forms
PROFILE_FIELDS: list[dict[str, Any]] = [
    {"key": "full_name", "label": "Full Name", "type": "text"},
    {"key": "email", "label": "Email", "type": "email"},
    {"key": "phone", "label": "Phone", "type": "tel"},
    {"key": "dob", "label": "Date of Birth", "type": "date", "format": "yyyy/mm/dd"},
    {"key": "id_number", "label": "National ID Number", "type": "text"},
    {"key": "id_expiry", "label": "ID Expiry", "type": "date", "format": "yyyy/mm/dd"},
    {"key": "passport", "label": "Passport Number", "type": "text"},
    {"key": "passport_expiry", "label": "Passport Expiry", "type": "date", "format": "yyyy/mm/dd"},
    {"key": "nationality", "label": "Nationality", "type": "text"},
    {"key": "address", "label": "Address", "type": "text"},
]

_ALLOWED_KEYS = {f["key"] for f in PROFILE_FIELDS}


def field_meta() -> list[dict[str, Any]]:
    """The field definitions for the UI (labels, types, formats)."""
    return [dict(f) for f in PROFILE_FIELDS]


def load_profile() -> dict[str, str]:
    """Return the saved profile (empty dict if none / unreadable)."""
    with _LOCK:
        if not PROFILE_PATH.is_file():
            return {}
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    if not isinstance(data, dict):
        return {}
    # Keep only known keys, coerce to trimmed strings.
    return {k: str(v).strip() for k, v in data.items() if k in _ALLOWED_KEYS and str(v).strip()}


def save_profile(values: dict[str, Any]) -> dict[str, str]:
    """Replace the profile with `values` (only known, non-empty keys are kept)."""
    clean = {k: str(v).strip() for k, v in (values or {}).items()
             if k in _ALLOWED_KEYS and str(v).strip()}
    with _LOCK:
        PROFILE_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def update_profile(partial: dict[str, Any]) -> dict[str, str]:
    """Merge `partial` into the saved profile (used when the user lets us remember a field)."""
    current = load_profile()
    current.update({k: str(v).strip() for k, v in (partial or {}).items()
                    if k in _ALLOWED_KEYS and str(v).strip()})
    return save_profile(current)


# --------------------------------------------------------------------------- #
# ID card image -> profile fields, via vision model. The user uploads a photo
# of their ID card and the model reads the fields to fill the profile.
# --------------------------------------------------------------------------- #
_DATE_KEYS = {f["key"] for f in PROFILE_FIELDS if f.get("type") == "date"}

# Map the various keys the model might return onto our canonical profile keys.
_KEY_ALIASES = {
    "name": "full_name", "fullname": "full_name", "holder": "full_name", "holder_name": "full_name",
    "id": "id_number", "id_number": "id_number", "idnumber": "id_number",
    "card_number": "id_number", "civil_id": "id_number", "national_id": "id_number",
    "serial": "id_number", "serial_number": "id_number",
    "date_of_birth": "dob", "birth_date": "dob", "dateofbirth": "dob", "birthdate": "dob",
    "expiry": "id_expiry", "expiry_date": "id_expiry", "id_expiry": "id_expiry",
    "expiration": "id_expiry", "expiration_date": "id_expiry", "card_expiry": "id_expiry",
    "passport_number": "passport", "passport_no": "passport", "passportnumber": "passport",
    "country": "nationality", "nationality_country": "nationality",
}

# Single-step fallback: ask the vision model for JSON directly.
_ID_VISION_PROMPT = (
    "Extract these things if available: Full Name, ID Number, Nationality, ID expiry Date, "
    "Passport Number fields in the form of json. Respond with only the JSON object."
)

# Two-step extraction (more reliable than asking the vision model for JSON directly):
#   1) the VISION model transcribes ALL text on the card (OCR);
#   2) the TEXT model turns that transcript into structured JSON fields.
_ID_OCR_PROMPT = (
    "This is a photo of an ID card. Read and transcribe ALL the text you can see on the "
    "card exactly as written — include every printed label together with its value (e.g. 'ID Number: "
    "...', 'Name: ...', 'Nationality: ...', 'Date of Birth: ...', 'Expiry: ...'). Do not summarise."
)
_ID_FIELD_SYSTEM = (
    "You extract structured fields from the raw text of an ID card. Return ONLY a JSON "
    "object (no prose, no markdown fences, no comments) using these keys when the value is present: "
    "full_name, id_number, nationality, dob, id_expiry, passport. "
    "IMPORTANT: every value MUST be in ENGLISH. If a value appears only in another language, "
    "translate or transliterate it into English. Format every date as yyyy-mm-dd and "
    "write numbers as digits. Omit any key you cannot find. If nothing is found, return {}."
)


def _coerce_text(raw: Any) -> str:
    """Vision/chat content occasionally arrives as a list of parts — coerce to a plain string."""
    if isinstance(raw, list):
        raw = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
    return str(raw or "").strip()


# ── Alias / replacement helpers for when the text model returns its own keys ──

def _apply_aliases(raw: dict[str, str]) -> dict[str, str]:
    """Map non-canonical keys (e.g. 'name' -^ 'full_name') so the profile store accepts them."""
    out: dict[str, str] = {}
    for k, v in raw.items():
        canonical = _KEY_ALIASES.get(k.lower().strip(), k)
        out[canonical] = v
    return out


# ── API called by the backend routes ──────────────────────────────────────────

def extract_fields_from_vision(raw: Any) -> dict[str, str]:
    """Coerce the raw OCR from the vision model and pick out known fields."""
    text = _coerce_text(raw)
    if not text:
        return {}
    # The two-step path returns JSON from the text model; parse if present.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return _apply_aliases({k: str(v).strip() for k, v in parsed.items() if isinstance(v, str)})
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: heuristic extraction from OCR text.
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        for alias, canonical in _KEY_ALIASES.items():
            if alias in line.lower():
                # Try to get the value after the label separator
                parts = line.split(":", 1)
                if len(parts) == 2:
                    val = parts[1].strip()
                    if val:
                        result[canonical] = val
                        break
    return result


# ── Public endpoint called by backend routes ──────────────────────────────────

def extract_from_image(client: Any, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """Extract profile fields from an ID card photo using vision + text models.

    Uses a two-step pipeline:
      1) Vision model transcribes all visible text on the card.
      2) Text model turns the transcript into structured JSON fields.
    Falls back to a single-step vision-to-JSON prompt if the two-step fails.
    """
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64}"

    # Step 1: OCR via vision model (Gemini see_image)
    try:
        raw_ocr = client.see_image(data_uri, _ID_OCR_PROMPT, max_tokens=1024)
    except Exception:
        raw_ocr = ""

    if raw_ocr:
        # Step 2: structured extraction via text model
        try:
            structured = client.chat(
                [{"role": "system", "content": _ID_FIELD_SYSTEM},
                 {"role": "user", "content": f"OCR text:\n{raw_ocr}"}],
                temperature=0.1,
                max_tokens=512,
            )
            fields = extract_fields_from_vision(structured)
            if fields:
                return {"fields": fields}
        except Exception:
            pass

    # Single-step fallback: ask the vision model for JSON directly.
    try:
        raw = client.see_image(data_uri, _ID_VISION_PROMPT, max_tokens=512)
        fields = extract_fields_from_vision(raw)
        if fields:
            return {"fields": fields}
    except Exception:
        return {"fields": {}, "error": "Could not read the ID image. Try a clearer photo or enter fields manually."}

    return {"fields": {}, "error": "Could not read the ID image. Try a clearer photo or enter fields manually."}
