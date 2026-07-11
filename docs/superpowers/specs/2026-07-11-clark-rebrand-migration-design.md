# Clark — General-Purpose Web Agent: Rebrand & Migration Design

## Overview
Rename the project from "MERAB Agent / Fanar" to **Clark**. Replace all Fanar AI model dependencies with Google Gemini API (primary) and Fireworks AI DeepSeek (fallback). Remove Qatar-specific infrastructure (tracks, workbooks, desktop shell, voice, Arabic localization). Generalize the agent to work on any website.

## Scope
**Keep:** FastAPI backend, browser session, tool registry, ReAct agent loop, human-in-the-loop gates, Next.js frontend, screenshot preview, history, profile & credentials stores.

**Remove:** `fanar_client.py`, `tracks.py`, `desktop.py`, `desktop/` folder, `VoiceButton.tsx`, Arabic i18n, voice endpoints, Fanar env vars, `fanar_knowledge` tool, Qatar workflow/KB system, Electron shell.

**Create:** `llm_client.py` (Gemini primary + Fireworks fallback). Update `.env.example`, `requirements.txt`, `README.md`.

## Architecture
- **LLM layer:** `LLMClient` wraps Google Gemini SDK (`google-genai`). Falls back to Fireworks AI OpenAI-compatible endpoint for chat. No speech, guard, or translation — those are removed.
- **Agent loop:** Simplified ReAct — no track/wf auto-detection, no Arabic localization, no E-Services login flows. Model drives browser with general tools.
- **Models:** Chat = Gemini 2.0 Flash (primary), DeepSeek V3 via Fireworks (fallback). Vision = Gemini multimodal input (built into chat).
- **Frontend:** English-only. Remove VoiceButton, i18n system, Arabic references. Update branding to "Clark".

## Removed Features
- Voice I/O (STT/TTS)
- Desktop computer-use surface
- Arabic ↔ English translation / localization
- Qatar e-service deterministic workbooks
- Track-based persona switching
- AI safety guard (replaced with lightweight check)
- Fanar knowledge tool

## File Changes
See Section 2 of the design discussion for the full file map.

## Implementation Order
1. Create `llm_client.py` — the new LLM provider
2. Update `main.py` — remove voice, update imports, rename
3. Update `agent.py` — strip localization, desktop, workflows
4. Update `tools.py` — remove fanar_knowledge, desktop tools
5. Delete `tracks.py`, `desktop.py`, `fanar_client.py`
6. Update `workflows.py` — strip Qatar-specific content
7. Update `.env.example` and `requirements.txt`
8. Update frontend — rename, remove voice & i18n
9. Delete `desktop/` folder
10. Update `README.md`
11. Run `/review` for final project review
