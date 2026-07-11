"""
Saved Login Credentials store — an OPTIONAL "password manager" the agent reuses to
sign in to portals it has logged into before (mapped to the site, like Chrome).

Behaviour the user asked for:
  • When the agent logs in, the user can tick "Remember this login" — we then save the
    username + password mapped to the site's host.
  • Next time a login is needed for that same site, we use the saved login automatically
    (no prompt). The user can view / edit / delete saved logins in "My Credentials".

Storage: a single local JSON file under the agent workspace, keyed by host. This is a
LOCAL, single-user app — passwords are stored in plain text, never sent to the AI model,
and never logged. Only use this on your own device.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
from typing import Any
from urllib.parse import urlparse

WORKSPACE = pathlib.Path(os.getenv("AGENT_WORKSPACE", "agent_workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)
CREDENTIALS_PATH = WORKSPACE / "credentials.json"

_LOCK = threading.Lock()


def host_of(url: str) -> str:
    """The host key we map credentials to (e.g. 'eservices.moi.gov.qa'). Falls back to the
    raw string if it isn't a URL."""
    if not url:
        return ""
    try:
        netloc = urlparse(url if "//" in url else "//" + url).netloc.lower()
        return netloc or (url or "").strip().lower()
    except Exception:  # noqa: BLE001
        return (url or "").strip().lower()


def _load_raw() -> dict[str, dict[str, str]]:
    with _LOCK:
        if not CREDENTIALS_PATH.is_file():
            return {}
        try:
            data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return data if isinstance(data, dict) else {}


def _write_raw(data: dict[str, dict[str, str]]) -> None:
    with _LOCK:
        CREDENTIALS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_all() -> list[dict[str, str]]:
    """All saved logins, newest-style order (host, url, username, password, label)."""
    out: list[dict[str, str]] = []
    for host, rec in _load_raw().items():
        if not isinstance(rec, dict):
            continue
        out.append({
            "host": host,
            "url": rec.get("url", host),
            "username": rec.get("username", ""),
            "password": rec.get("password", ""),
            "label": rec.get("label", host),
        })
    return sorted(out, key=lambda r: r["host"])


def get_for_url(url: str) -> dict[str, str] | None:
    """Return the saved login whose host matches `url`, or None."""
    host = host_of(url)
    if not host:
        return None
    rec = _load_raw().get(host)
    if isinstance(rec, dict) and rec.get("username"):
        return {"host": host, "url": rec.get("url", url), "username": rec.get("username", ""),
                "password": rec.get("password", ""), "label": rec.get("label", host)}
    return None


def save(url: str, username: str, password: str, label: str = "") -> dict[str, str]:
    """Upsert a saved login for `url`'s host. No-op if username is empty."""
    host = host_of(url)
    username = (username or "").strip()
    if not host or not username:
        return {}
    data = _load_raw()
    data[host] = {"url": url or host, "username": username,
                  "password": password or "", "label": (label or host).strip()}
    _write_raw(data)
    return {"host": host, **data[host]}


def upsert(rec: dict[str, Any]) -> dict[str, str]:
    """Save/edit from the UI: keys url|host, username, password, label."""
    url = rec.get("url") or rec.get("host") or ""
    return save(url, rec.get("username", ""), rec.get("password", ""), rec.get("label", ""))


def delete(host: str) -> bool:
    data = _load_raw()
    key = host_of(host) if "//" in (host or "") else (host or "").strip().lower()
    if key in data:
        data.pop(key, None)
        _write_raw(data)
        return True
    return False
