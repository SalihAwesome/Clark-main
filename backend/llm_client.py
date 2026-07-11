"""
LLM client — Fireworks AI (primary) + Google Gemini (fallback).

Capabilities:
  • Chat (streaming + non-streaming) — drives the agent's ReAct loop
  • Vision (multimodal) — Fireworks kimi-k2p6 or Gemini fallback
  • Automatic fallback — if Fireworks is unreachable, retries on Gemini

Configuration (env vars):
  FIREWORKS_API_KEY          — required (primary)
  FIREWORKS_MODEL            — default "accounts/fireworks/models/deepseek-v4-pro"
  FIREWORKS_VISION_MODEL     — default "accounts/fireworks/models/kimi-k2p6"
  GEMINI_API_KEY             — optional (fallback)
  GEMINI_MODEL               — default "gemini-2.0-flash"
  LLM_TIMEOUT                — per-call timeout in seconds (default 75)
"""

from __future__ import annotations

import base64
import os
import re
import threading
import time
from typing import Any, Iterator

import httpx


class LLMError(RuntimeError):
    """Raised when all LLM providers are unreachable or return an error."""


def _decode_base64(data_url: str) -> tuple[bytes, str]:
    """Decode a base64 data URL like 'data:image/png;base64,...' -> (bytes, mime)."""
    m = re.match(r"data:([^;]+);base64,(.+)", data_url)
    if m:
        return base64.b64decode(m.group(2)), m.group(1)
    return b"", "image/png"


class LLMClient:
    """Dual-provider LLM client: Fireworks primary, Gemini OpenAI-compat fallback."""

    def __init__(self) -> None:
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.fireworks_api_key = os.getenv("FIREWORKS_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.fireworks_model = os.getenv("FIREWORKS_MODEL",
                                         "accounts/fireworks/models/deepseek-v4-pro")
        self.fireworks_vision_model = os.getenv("FIREWORKS_VISION_MODEL",
                                                "accounts/fireworks/models/kimi-k2p6")

        self.timeout = float(os.getenv("LLM_TIMEOUT", "75"))
        self.fast_timeout = float(os.getenv("LLM_FAST_TIMEOUT", "15"))

        # Circuit breaker: mark a provider down for this many seconds
        self._down_models: dict[str, float] = {}
        self._down_ttl = float(os.getenv("LLM_DOWN_TTL", "180"))
        self._down_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Readiness
    # ------------------------------------------------------------------ #
    @property
    def configured(self) -> bool:
        return bool(self.fireworks_api_key) or bool(self.gemini_api_key)

    @property
    def default_model(self) -> str:
        """Which model name we advertise to the frontend / health check."""
        if self.fireworks_api_key:
            return f"fireworks:{self.fireworks_model}"
        if self.gemini_api_key:
            return f"gemini:{self.gemini_model}"
        return "none"

    @property
    def vision_model(self) -> str:
        if self.fireworks_api_key:
            return f"fireworks:{self.fireworks_vision_model}"
        if self.gemini_api_key:
            return f"gemini:{self.gemini_model}"
        return "none"

    @staticmethod
    def _is_transient(exc: LLMError) -> bool:
        s = str(exc).lower()
        if "could not reach" in s or "timeout" in s or "timed out" in s:
            return True
        m = re.search(r"error (\d{3})", s)
        return bool(m and 500 <= int(m.group(1)) < 600)

    def _mark_down(self, provider: str) -> None:
        with self._down_lock:
            self._down_models[provider] = time.monotonic()

    def _is_down(self, provider: str) -> bool:
        now = time.monotonic()
        with self._down_lock:
            return now - self._down_models.get(provider, -1e9) < self._down_ttl

    # ------------------------------------------------------------------ #
    # Gemini (fallback)
    # ------------------------------------------------------------------ #
    def _gemini_chat(self, messages: list[dict[str, Any]], temperature: float,
                     max_tokens: int, timeout: float) -> str:
        """Non-streaming chat via the Gemini API (REST)."""
        # Convert our message format to Gemini's contents format
        system = ""
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                contents.append({"role": "user" if role == "user" else "model",
                                 "parts": [{"text": content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.gemini_model}:generateContent?key={self.gemini_api_key}")
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Gemini API: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response: {data}") from exc

    def _gemini_chat_stream(self, messages: list[dict[str, Any]], temperature: float,
                            max_tokens: int, timeout: float) -> Iterator[str]:
        """Streaming chat via the Gemini API (REST stream)."""
        system = ""
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                contents.append({"role": "user" if role == "user" else "model",
                                 "parts": [{"text": content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.gemini_model}:streamGenerateContent?alt=sse&key={self.gemini_api_key}")
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code >= 400:
                        body = resp.read().decode("utf-8", "replace")
                        raise LLMError(f"Gemini API error {resp.status_code}: {body[:500]}")
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        import json
                        try:
                            chunk = json.loads(data_str)
                            text = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text:
                                yield text
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Gemini API: {exc}") from exc

    def _gemini_vision(self, image_b64: str, prompt: str, max_tokens: int) -> str:
        """Multimodal chat — ask Gemini about an image (base64 data URL)."""
        img_bytes, mime = _decode_base64(image_b64)
        b64_str = base64.b64encode(img_bytes).decode()

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime, "data": b64_str}},
                ],
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.gemini_model}:generateContent?key={self.gemini_api_key}")
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Gemini vision API: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Gemini vision error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini vision response: {data}") from exc

    # ------------------------------------------------------------------ #
    # Fireworks (primary) — OpenAI-compatible
    # ------------------------------------------------------------------ #
    def _fireworks_chat(self, messages: list[dict[str, Any]], temperature: float,
                        max_tokens: int, timeout: float) -> str:
        payload = {
            "model": self.fireworks_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    "https://api.fireworks.ai/inference/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.fireworks_api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Fireworks API: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Fireworks API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Fireworks response: {data}") from exc

    def _fireworks_chat_stream(self, messages: list[dict[str, Any]], temperature: float,
                               max_tokens: int, timeout: float) -> Iterator[str]:
        import json
        payload = {
            "model": self.fireworks_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST", "https://api.fireworks.ai/inference/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.fireworks_api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    if resp.status_code >= 400:
                        body = resp.read().decode("utf-8", "replace")
                        raise LLMError(f"Fireworks API error {resp.status_code}: {body[:500]}")
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"].get("content")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Fireworks API: {exc}") from exc

    def _fireworks_vision(self, image_b64: str, prompt: str, max_tokens: int) -> str:
        """Multimodal via Fireworks (OpenAI-compatible vision API)."""
        import json
        img_bytes, mime = _decode_base64(image_b64)
        b64_str = base64.b64encode(img_bytes).decode()
        data_uri = f"data:{mime};base64,{b64_str}"
        payload = {
            "model": self.fireworks_vision_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    "https://api.fireworks.ai/inference/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.fireworks_api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Fireworks vision API: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Fireworks vision error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Fireworks vision response: {data}") from exc

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def chat(self, messages: list[dict[str, Any]], model: str | None = None,
             temperature: float = 0.2, max_tokens: int = 1024,
             timeout: float | None = None, **kwargs: Any) -> str:
        """Non-streaming chat. Tries Fireworks first, falls back to Gemini."""
        last_exc: LLMError | None = None
        tout = timeout or self.timeout

        # Try Fireworks (primary)
        if self.fireworks_api_key and not self._is_down("fireworks"):
            try:
                return self._fireworks_chat(messages, temperature, max_tokens, tout)
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("fireworks")
                else:
                    raise

        # Fallback to Gemini
        if self.gemini_api_key and not self._is_down("gemini"):
            try:
                return self._gemini_chat(messages, temperature, max_tokens, tout)
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("gemini")
                else:
                    raise

        raise last_exc or LLMError("No LLM provider available — set FIREWORKS_API_KEY or GEMINI_API_KEY.")

    def chat_stream(self, messages: list[dict[str, Any]], model: str | None = None,
                    temperature: float = 0.2, max_tokens: int = 1024,
                    **kwargs: Any) -> Iterator[str]:
        """Streaming chat. Tries Fireworks first, falls back to Gemini."""
        last_exc: LLMError | None = None

        if self.fireworks_api_key and not self._is_down("fireworks"):
            try:
                yielded = False
                for delta in self._fireworks_chat_stream(messages, temperature, max_tokens, self.timeout):
                    yielded = True
                    yield delta
                return
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("fireworks")
                if yielded:
                    return  # partial content already delivered; can't cleanly switch providers mid-stream

        if self.gemini_api_key and not self._is_down("gemini"):
            try:
                for delta in self._gemini_chat_stream(messages, temperature, max_tokens, self.timeout):
                    yield delta
                return
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("gemini")
                else:
                    raise

        raise last_exc or LLMError("No LLM provider available.")

    def see_image(self, image_b64: str, prompt: str, max_tokens: int = 400,
                  mime_type: str = "image/png") -> str:
        """Ask about an image via multimodal vision. Fireworks primary (kimi-k2p6), Gemini fallback."""
        last_exc: LLMError | None = None

        if self.fireworks_api_key and not self._is_down("fireworks"):
            try:
                return self._fireworks_vision(image_b64, prompt, max_tokens)
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("fireworks")

        if self.gemini_api_key and not self._is_down("gemini"):
            try:
                return self._gemini_vision(image_b64, prompt, max_tokens)
            except LLMError as exc:
                last_exc = exc
                if self._is_transient(exc):
                    self._mark_down("gemini")

        raise last_exc or LLMError("No LLM provider available for vision calls.")
