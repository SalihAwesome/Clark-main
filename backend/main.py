"""
FastAPI backend for Clark — a general-purpose autonomous web agent.

Endpoints:
  GET  /api/health             -> service + LLM status
  GET  /api/capabilities       -> available tools
  POST /api/chat               -> plain streaming chat (SSE)
  POST /api/agent              -> agentic loop (SSE)
  POST /api/agent/resume       -> continue after a human pause
  GET  /api/screenshot/{name}  -> PNG frame the agent captured
  POST /api/session/close      -> close a session's browser
  GET  /api/workspace          -> artefacts the agent created

Run:  uvicorn main:app --reload --port 8008
"""

from __future__ import annotations

import base64
import json
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

load_dotenv()

import audit  # noqa: E402
from agent import AgentRun  # noqa: E402
from browser_session import SHOTS_DIR, close_session, get_session  # noqa: E402
from llm_client import LLMClient, LLMError  # noqa: E402
import credentials_store  # noqa: E402
import payment_store  # noqa: E402
from profile_store import (  # noqa: E402
    extract_from_image, field_meta, load_profile, save_profile, update_profile)
from tools import WORKSPACE  # noqa: E402

app = FastAPI(title="Clark Agent API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# CORS is open because this is a local-only dev tool. Do NOT expose port 8008 on a network.

client = LLMClient()

# ── Startup validation ────────────────────────────────────────────────
if not client.configured:
    import warnings
    warnings.warn(
        "No LLM provider configured. Set GEMINI_API_KEY (and optionally FIREWORKS_API_KEY) "
        "in backend/.env"
    )

RUNS: dict[str, AgentRun] = {}


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []
    session_id: str = "default"
    lang: str = "en"


class ResumeRequest(BaseModel):
    session_id: str = "default"
    note: str = ""


class CredentialsRequest(BaseModel):
    session_id: str = "default"
    credentials: dict[str, str] = {}
    remember: bool = False


class SavedCredentialRequest(BaseModel):
    url: str = ""
    host: str = ""
    username: str = ""
    password: str = ""
    label: str = ""


class ProfileRequest(BaseModel):
    values: dict[str, str] = {}


class InputsRequest(BaseModel):
    session_id: str = "default"
    values: dict[str, str] = {}
    save_keys: list[str] = []


class CaptchaRequest(BaseModel):
    session_id: str = "default"
    code: str = ""


class OtpRequest(BaseModel):
    session_id: str = "default"
    code: str = ""


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _agent_sse(run: AgentRun) -> StreamingResponse:
    def gen():
        yield ": connected\n\n"
        try:
            for event in run.run():
                if event.get("type") != "delta":
                    run.record({k: v for k, v in event.items() if k != "image"} if "image" in event else event)
                yield _sse(event)
            yield _sse({"type": "done"})
        except Exception as exc:
            ev = {"type": "error", "content": f"Agent failure: {exc}"}
            run.record(ev)
            yield _sse(ev)
        finally:
            try:
                audit.save(run)
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm_configured": client.configured, "model": client.default_model}


@app.get("/api/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "models": {"chat": client.default_model, "vision": client.vision_model},
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    messages = [{"role": "system", "content": "You are Clark, a helpful autonomous web agent. Answer clearly and concisely, using Markdown when it helps (headings, lists, bold)."}]
    messages += [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})
    convo = [{"role": m.role, "content": m.content} for m in req.history]
    convo.append({"role": "user", "content": req.message})

    def gen():
        yield ": connected\n\n"
        answer = ""
        try:
            for delta in client.chat_stream(messages, temperature=0.3, max_tokens=1024):
                answer += delta
                yield _sse({"type": "delta", "content": delta})
            yield _sse({"type": "done"})
        except LLMError:
            msg = "⚠️ The AI service isn't responding right now — please try again in a moment."
            yield _sse({"type": "delta", "content": msg})
            yield _sse({"type": "final", "content": msg})
            yield _sse({"type": "done"})
        finally:
            try:
                if answer.strip():
                    convo.append({"role": "assistant", "content": answer})
                    audit.save_chat(req.session_id, convo)
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.post("/api/agent")
def agent(req: ChatRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        run = AgentRun(req.session_id, client, lang=req.lang)
        RUNS[req.session_id] = run
    run.add_user_message(req.message, history=[m.model_dump() for m in req.history])
    return _agent_sse(run)


@app.post("/api/agent/resume")
def agent_resume(req: ResumeRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No active agent run to resume.")
    run.resume(req.note)
    return _agent_sse(run)


@app.post("/api/agent/credentials")
def agent_credentials(req: CredentialsRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No active agent run.")
    run.set_credentials(req.credentials, remember=req.remember)
    return _agent_sse(run)


@app.post("/api/agent/inputs")
def agent_inputs(req: InputsRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No active agent run.")
    run.provide_inputs(req.values, req.save_keys)
    return _agent_sse(run)


@app.post("/api/agent/captcha")
def agent_captcha(req: CaptchaRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No active agent run.")
    run.provide_captcha(req.code)
    return _agent_sse(run)


@app.post("/api/agent/otp")
def agent_otp(req: OtpRequest) -> StreamingResponse:
    run = RUNS.get(req.session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No active agent run.")
    run.provide_otp(req.code)
    return _agent_sse(run)


@app.post("/api/agent/stop")
def agent_stop(req: ResumeRequest) -> dict[str, Any]:
    run = RUNS.get(req.session_id)
    if run is None:
        return {"stopped": False, "reason": "no active run"}
    run.cancel()
    try:
        audit.save(run)
    except Exception:
        pass
    return {"stopped": True, "session_id": req.session_id}


@app.get("/api/history")
def get_history() -> dict[str, Any]:
    return {"conversations": audit.list_all()}


@app.get("/api/history/{conv_id}")
def get_history_item(conv_id: str) -> dict[str, Any]:
    rec = audit.get(conv_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return rec


@app.delete("/api/history/{conv_id}")
def delete_history_item(conv_id: str) -> dict[str, Any]:
    return {"deleted": audit.delete(conv_id)}


@app.get("/api/profile")
def get_profile() -> dict[str, Any]:
    return {"fields": field_meta(), "values": load_profile()}


@app.put("/api/profile")
def put_profile(req: ProfileRequest) -> dict[str, Any]:
    return {"ok": True, "values": save_profile(req.values)}


@app.post("/api/profile/extract")
async def profile_extract(file: UploadFile = File(...), save: bool = Form(True)) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    result = extract_from_image(client, data, mime_type=file.content_type or "image/jpeg")
    fields = result.get("fields", {})
    values = update_profile(fields) if (save and fields) else load_profile()
    return {"fields": fields, "values": values, "error": result.get("error")}


@app.get("/api/credentials")
def get_credentials() -> dict[str, Any]:
    return {"credentials": credentials_store.list_all()}


@app.put("/api/credentials")
def put_credential(req: SavedCredentialRequest) -> dict[str, Any]:
    saved = credentials_store.upsert(req.model_dump())
    return {"ok": bool(saved), "credentials": credentials_store.list_all()}


@app.delete("/api/credentials/{host}")
def delete_credential(host: str) -> dict[str, Any]:
    return {"deleted": credentials_store.delete(host), "credentials": credentials_store.list_all()}


@app.get("/api/payment")
def get_payment() -> dict[str, Any]:
    return {"fields": payment_store.field_meta(), "values": payment_store.load_payment()}


@app.put("/api/payment")
def put_payment(req: ProfileRequest) -> dict[str, Any]:
    return {"ok": True, "values": payment_store.save_payment(req.values)}


@app.get("/api/screenshot/{name}")
def screenshot(name: str) -> FileResponse:
    path = (SHOTS_DIR / name).resolve()
    if SHOTS_DIR not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/png")


_BLANK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@app.get("/api/agent/screen/{session_id}")
def agent_screen(session_id: str) -> Response:
    sess = get_session(session_id, create=False)
    png = sess.live_screenshot() if sess else b""
    return Response(content=png or _BLANK_PNG, media_type="image/png",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.post("/api/session/close")
def session_close(req: ResumeRequest) -> dict[str, Any]:
    RUNS.pop(req.session_id, None)
    return {"closed": close_session(req.session_id), "session_id": req.session_id}


@app.get("/api/workspace")
def list_workspace() -> dict[str, Any]:
    files = [{"name": p.name, "bytes": p.stat().st_size} for p in sorted(WORKSPACE.glob("*")) if p.is_file()]
    return {"workspace": str(WORKSPACE), "files": files}
