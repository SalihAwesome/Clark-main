"""
Conversation audit trail + history.

Every agent conversation is persisted to a JSON file under agent_workspace/audit/.
The record captures the full, transparent transcript — the user's prompt, every
thought/action/observation/screenshot the agent produced, any human gates, and the
final answer — so you can always look back at exactly what was done.

History is just the list of those records, newest first.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import threading
from typing import Any

WORKSPACE = pathlib.Path(os.getenv("AGENT_WORKSPACE", "agent_workspace")).resolve()
AUDIT_DIR = WORKSPACE / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

_LOCK = threading.Lock()


def _safe_id(conv_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", conv_id or "conversation")[:80]


def _status(run: Any) -> str:
    if getattr(run, "_cancelled", False):
        return "stopped"
    if getattr(run, "awaiting", False):
        return "paused"
    # A final/stopped event in the transcript means the run finished a turn.
    for ev in reversed(getattr(run, "transcript", [])):
        if ev.get("type") in ("final", "delta"):
            return "completed"
    return "in_progress"


def save(run: Any) -> dict[str, Any]:
    """Write/overwrite the audit record for a run's conversation. Returns the summary."""
    conv_id = _safe_id(run.session_id)
    transcript = list(getattr(run, "transcript", []))
    prompts = [e["content"] for e in transcript if e.get("type") == "prompt"]
    # Final answer = last final event's content, or accumulated deltas.
    final = ""
    for ev in reversed(transcript):
        if ev.get("type") == "final" and ev.get("content"):
            final = ev["content"]
            break
    record = {
        "id": conv_id,
        "title": getattr(run, "title", "") or (prompts[0] if prompts else "Conversation"),
        "created_at": getattr(run, "created_at", ""),
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": _status(run),
        "track": getattr(run, "track", ""),
        "surface": getattr(run, "surface", ""),
        "mode": "agent",
        "prompts": prompts,
        "final": final,
        "num_steps": getattr(run, "steps", 0),
        "num_actions": sum(1 for e in transcript if e.get("type") == "action"),
        "transcript": transcript,
    }
    with _LOCK:
        (AUDIT_DIR / f"{conv_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return _summary(record)


def save_chat(session_id: str, messages: list[dict[str, Any]],
              track: str = "", surface: str = "") -> dict[str, Any]:
    """Persist a CHAT-mode conversation (plain Q&A, no agent trace). `messages` is the FULL
    conversation so far ([{role, content}, …]); called each turn and overwrites the same record,
    so it always holds the complete transcript. created_at is preserved across turns."""
    conv_id = _safe_id(session_id)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    created_at = ""
    existing = AUDIT_DIR / f"{conv_id}.json"
    if existing.is_file():
        try:
            created_at = json.loads(existing.read_text(encoding="utf-8")).get("created_at", "")
        except (json.JSONDecodeError, OSError):
            created_at = ""
    transcript: list[dict[str, Any]] = []
    prompts: list[str] = []
    for m in messages or []:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            transcript.append({"type": "prompt", "content": content})
            prompts.append(content)
        elif role == "assistant":
            transcript.append({"type": "answer", "content": content})
    final = ""
    for m in reversed(messages or []):
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            final = m["content"]
            break
    record = {
        "id": conv_id,
        "title": (prompts[0] if prompts else "Chat")[:120],
        "created_at": created_at or now,
        "updated_at": now,
        "status": "completed",
        "track": track,
        "surface": surface,
        "mode": "chat",
        "prompts": prompts,
        "final": final,
        "num_steps": len(prompts),
        "num_actions": 0,
        "transcript": transcript,
    }
    with _LOCK:
        (AUDIT_DIR / f"{conv_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return _summary(record)


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record.get(k) for k in
            ("id", "title", "created_at", "updated_at", "status", "track",
             "surface", "mode", "num_steps", "num_actions", "final")}


def list_all() -> list[dict[str, Any]]:
    """All conversation summaries, newest first."""
    out: list[dict[str, Any]] = []
    with _LOCK:
        files = list(AUDIT_DIR.glob("*.json"))
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            out.append(_summary(rec))
        except (json.JSONDecodeError, OSError):
            continue
    out.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return out


def get(conv_id: str) -> dict[str, Any] | None:
    """The full audit record (incl. transcript) for one conversation."""
    path = AUDIT_DIR / f"{_safe_id(conv_id)}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete(conv_id: str) -> bool:
    path = AUDIT_DIR / f"{_safe_id(conv_id)}.json"
    try:
        path.unlink()
        return True
    except OSError:
        return False
