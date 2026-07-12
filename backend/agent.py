"""
The agentic orchestration loop — general-purpose, human-in-the-loop.

Capabilities:
  • Drives a real browser (search, navigate, read, fill forms).
  • ReAct-style JSON protocol: each turn the model emits ONE JSON object
    (a tool call or a final answer); we parse it, run the tool, feed back
    the observation, repeat.

Human-in-the-loop gates:
  • Sign-in credentials (secure modal, never sent to the model)
  • One-time codes (OTP) and verification codes (captcha)
  • Payment review and confirmation
"""

from __future__ import annotations

import datetime
import json
import re
import time
from typing import Any, Iterator

import credentials_store
import profile_store
import tools as tools_mod
from llm_client import LLMClient, LLMError


MAX_STEPS = 28


def _shortdesc(d: str) -> str:
    d = (d or "").split(". ")[0].strip()
    return d[:90]


def _system_prompt() -> str:
    schemas = tools_mod.TOOL_SCHEMAS
    tool_lines = "\n".join(
        f"- {s['name']}({', '.join(s['args'].keys())}): {_shortdesc(s['description'])}"
        for s in schemas
    )
    return f"""You are Clark, an autonomous web agent. Reply with ONE JSON object only — no other text.

Call tool:  {{"thought":"...","action":"TOOL_NAME","action_input":{{...}}}}
Final:      {{"thought":"...","final_answer":"..."}}

RULES:
1. First reply is always a tool call. Never answer from memory.
2. NEVER open article/research paper pages — they load minimal text (truncated). Use web_search for snippets, or arxiv_search for full abstracts.
3. If "blocked" or "truncated" appears, move on immediately with what you have.
4. Forms/registration: navigate → see_page → fill marks → submit. Use demoqa.com/automation-practice-form for testing forms, or the-internet.herokuapp.com/login for login forms. Use pause_for_user for CAPTCHA.
5. Research papers: arxiv_search(paper_id=...) returns the full abstract. Wikipedia: open_page ONCE → see_page → read the provided content — it is clipped to ~15K chars but that is enough. Do NOT try mobile/printable/simple Wikipedia variants; they also clip. If you need the full text, web_search for "Wikipedia article on X" and compile a summary from snippets.
6. Do what the user asks. If they ask you to "save a document" or "save a summary as a document", ALWAYS produce BOTH a final_answer with the content/answer AND call save_document(filename, content) — never one without the other. Do NOT ask "what would you like me to do next" — just do it.
7. Near step {MAX_STEPS-2}/{MAX_STEPS}: deliver a partial final_answer with whatever you have.
8. NEVER output prose, markdown, or thinking — only JSON. Do NOT have a conversation. Do NOT ask the user what to do next.
9. If web_search returns 0 results (empty results list), do NOT retry the same search — instead use open_page with a relevant URL (e.g. open a news site directly for news, or the relevant service page) to find content on the page itself.

Tools:
{tool_lines}

Examples:
{{"thought":"search first","action":"web_search","action_input":{{"query":"latest ai news"}}}}
{{"thought":"got results","final_answer":"Here are the latest AI news stories: ..."}}
{{"thought":"research paper","action":"arxiv_search","action_input":{{"paper_id":"2410.12412"}}}}
{{"thought":"visit Wikipedia","action":"open_page","action_input":{{"url":"https://en.wikipedia.org/wiki/Artificial_intelligence"}}}}"""


_SMALLTALK = (
    "hi", "hii", "hey", "hello", "helo", "yo", "hiya", "sup", "thanks", "thank you", "thx",
    "ok", "okay", "cool", "nice", "great", "good morning", "good evening", "good night",
    "how are you", "whats up", "what's up", "who are you", "what can you do", "help",
)


def _is_smalltalk(text: str) -> bool:
    t = (text or "").strip().lower().strip("?!.,")
    if len(t) > 40:
        return False
    return t in _SMALLTALK or any(t == g or t.startswith(g + " ") for g in _SMALLTALK)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start: i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _trim(result: dict[str, Any]) -> dict[str, Any]:
    """Keep observations SMALL to fit model context windows."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    out.pop("screenshot", None)
    if isinstance(out.get("elements"), list):
        out["elements"] = [{"n": e.get("n"), "t": (e.get("type") or e.get("tag")),
                            "label": (e.get("label") or "")[:28]} for e in out["elements"][:22]]
        if "text" in out:
            out["text"] = (out["text"] or "")[:1200]
    elif isinstance(out.get("text"), str) and len(out["text"]) > 3000:
        out["text"] = out["text"][:3000] + " …"
    if isinstance(out.get("understanding"), str) and len(out["understanding"]) > 400:
        out["understanding"] = out["understanding"][:400] + " …"
    return out


def _verify_note(tool: str, result: dict[str, Any]) -> str:
    """Tell the model whether the action actually worked, so it self-corrects."""
    if not isinstance(result, dict):
        return ""
    if result.get("error"):
        return f" The tool ERRORED: {result['error']} — try a different element or approach."
    if result.get("blocked"):
        return (f" BLOCKED: {result['blocked']}. The site is not rendering real content. "
                f"Move on to a DIFFERENT site or try a different approach — do NOT retry the same page.")
    if result.get("truncated"):
        return (f" TRUNCATED: {result['truncated']}. The real content is behind a paywall or "
                f"JS wall — move on to a different site immediately. Do NOT retry or interact with this page.")
    if result.get("page_error"):
        return (f" WARNING: the page shows an error — '{result['page_error']}'. The step did NOT "
                f"succeed; fix it or try another way. Do NOT proceed as if it worked.")
    if result.get("login_succeeded") is False:
        return (" WARNING: still on the login page — sign-in did NOT go through (wrong credentials, "
                "or an OTP/2FA/CAPTCHA step). Re-read the page; if it needs OTP/captcha call pause_for_user.")
    if result.get("changed") is False and tool in ("click_mark", "click"):
        return (" WARNING: the page did NOT change after that click — it may not have worked. "
                "Try a different box or approach; do not assume success.")
    if tool == "web_search" and isinstance(result.get("results"), list) and len(result["results"]) == 0:
        return (" The search returned 0 results. Try opening a relevant page directly with open_page() "
                "instead of retrying the same search.")
    return ""


class AgentRun:
    """A resumable agent conversation bound to a session and browser."""

    def __init__(self, session_id: str, client: LLMClient, lang: str = "en") -> None:
        self.session_id = session_id
        self.client = client
        self.lang = (lang or "en").lower()
        self.messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt()}]
        self.steps = 0
        self.awaiting = False
        self._tools_used = 0
        self._corrections = 0
        self._pending_action: tuple[str, dict[str, Any]] | None = None
        self._approved = False
        self._user_declined = False
        self._credentials: dict[str, str] = {}
        self._login_requested = False
        self._login_url = ""
        self._last_page_url = ""
        self._smalltalk = False
        self._last_user = ""
        self._do_login = False
        self._post_login_url = ""
        self._captcha_code = ""
        self._otp_code = ""
        self._cancelled = False
        self.created_at = datetime.datetime.now().isoformat(timespec="seconds")
        self.title = ""
        self.transcript: list[dict[str, Any]] = []

    def cancel(self) -> None:
        self._cancelled = True

    def record(self, event: dict[str, Any]) -> None:
        self.transcript.append({**event, "ts": datetime.datetime.now().isoformat(timespec="seconds")})

    def add_user_message(self, message: str, history: list[dict[str, str]] | None = None) -> None:
        if len(self.messages) == 1:
            for turn in history or []:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    self.messages.append({"role": turn["role"], "content": turn["content"]})
        self._last_user = message
        self._smalltalk = _is_smalltalk(message)
        if not self.title:
            self.title = message.strip()[:120]
        self.record({"type": "prompt", "content": message})
        self._cancelled = False

        if self._smalltalk:
            self.messages.append({"role": "user", "content": message})
        else:
            self.messages.append({
                "role": "user",
                "content": f"{message}\n\n(Respond with ONE JSON object. Begin by using a tool — do not answer from memory.)",
            })
        self.awaiting = False
        self._tools_used = 0
        self._corrections = 0
        self._pending_action = None
        self._login_requested = False
        self.steps = 0

    def resume(self, note: str) -> None:
        low = (note or "").strip().lower()
        declined = any(w in low for w in ("no", "don't", "dont", "cancel", "reject", "stop",
                                          "skip", "decline", "abort"))
        self._approved = not declined
        self.awaiting = False
        if declined:
            self._user_declined = True
            self._pending_action = None
            self._do_login = False
            return
        self.messages.append({
            "role": "user",
            "content": f"The user approved/completed the step{(': ' + note) if note else ''}. Continue with the next JSON step.",
        })

    def set_credentials(self, creds: dict[str, str], remember: bool = False) -> None:
        self._credentials.update({k: v for k, v in (creds or {}).items() if v})
        self.awaiting = False
        self._do_login = True
        if remember and self._login_url and self._credentials.get("username"):
            try:
                credentials_store.save(self._login_url, self._credentials.get("username", ""),
                                       self._credentials.get("password", ""))
            except Exception:
                pass
        self.messages.append({
            "role": "user",
            "content": "The user has securely provided their login details (hidden from you). "
                       "I am signing them in now; after that, continue with the task — do not log in again.",
        })

    def _use_saved_login(self, url: str) -> bool:
        if self._credentials:
            return False
        saved = None
        try:
            saved = credentials_store.get_for_url(url)
        except Exception:
            saved = None
        if not saved:
            return False
        self._credentials.update({"username": saved.get("username", ""),
                                  "password": saved.get("password", "")})
        self._do_login = True
        self._login_requested = True
        self._login_url = url
        return True

    def provide_captcha(self, code: str) -> None:
        self._captcha_code = (code or "").strip()
        self.awaiting = False
        if not self._captcha_code:
            self._user_declined = True

    def provide_otp(self, code: str) -> None:
        self._otp_code = (code or "").strip()
        self.awaiting = False
        if not self._otp_code:
            self._user_declined = True

    def _dispatch(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return tools_mod.run_tool(tool, args, session_id=self.session_id, client=self.client,
                                  surface="web", credentials=self._credentials)

    def run(self) -> Iterator[dict[str, Any]]:
        yield from self._run_impl()

    def _run_impl(self) -> Iterator[dict[str, Any]]:
        if self._cancelled:
            yield {"type": "stopped", "content": "Stopped by user."}
            return

        if self._user_declined:
            self._user_declined = False
            self.awaiting = False
            msg = "No problem — I've stopped here since you cancelled that step. Nothing was submitted."
            yield {"type": "delta", "content": msg}
            yield {"type": "final", "content": msg}
            return

        if self.steps == 0 and self._smalltalk and not self._pending_action:
            yield from self._stream_smalltalk()
            return

        # If we paused for an action approval and the user approved, run it now.
        if self._pending_action and self._approved:
            tool, args = self._pending_action
            self._pending_action = None
            try:
                result = self._dispatch(tool, args)
            except Exception as exc:
                result = {"error": str(exc)}
            if isinstance(result, dict) and result.get("screenshot"):
                yield {"type": "screenshot", "url": result["screenshot"]}
            yield {"type": "observation", "tool": tool, "result": _trim(result)}
            self.messages.append({"role": "user", "content": f"Observation from {tool}: {json.dumps(_trim(result), ensure_ascii=False)}\nContinue."})

        # The user just provided credentials → sign in deterministically.
        if self._credentials and self._do_login and not self._pending_action:
            self._do_login = False
            yield from self._do_fill_login()
            if self.awaiting:
                return

        while self.steps < MAX_STEPS:
            if self._cancelled:
                yield {"type": "stopped", "content": "Stopped by user."}
                return
            self.steps += 1
            self._compact()

            # Force the model to hand in a final answer near the step limit.
            if self.steps == MAX_STEPS - 1:
                self.messages.append({"role": "user", "content":
                    f"[LIMIT] Step {self.steps}/{MAX_STEPS} — you MUST stop and deliver a JSON final_answer NOW:\n"
                    "{\"thought\":\"...\",\"final_answer\":\"what I found or what went wrong\"}\n"
                    "No more tool calls. A partial answer is better than silence."})

            try:
                raw = self.client.chat(self.messages, temperature=0.1, max_tokens=800)
            except LLMError as exc:
                if any(k in str(exc).lower() for k in ("too_large", "context", "413", "maximum")):
                    try:
                        raw = self.client.chat(self._fit(4500), temperature=0.1, max_tokens=256)
                    except LLMError:
                        yield {"type": "delta", "content": "⚠️ The AI service isn't responding right now — please try again in a moment."}
                        yield {"type": "final", "content": "⚠️ The AI service isn't responding right now — please try again in a moment."}
                        return
                else:
                    yield {"type": "delta", "content": "⚠️ The AI service isn't responding right now — please try again in a moment."}
                    yield {"type": "final", "content": "⚠️ The AI service isn't responding right now — please try again in a moment."}
                    return

            decision = _extract_json(raw)
            if decision is None or not (decision.get("action") or "final_answer" in decision):
                if self._corrections < 3:
                    self._corrections += 1
                    self.messages.append({"role": "assistant", "content": raw.strip()[:600]})
                    self.messages.append({"role": "user", "content": "Invalid. Reply with ONE valid JSON object — tool call or final_answer. Example:\n{\"thought\":\"...\",\"action\":\"web_search\",\"action_input\":{\"query\":\"...\"}}\nOr: {\"thought\":\"...\",\"final_answer\":\"...\"}\nJSON now:"})
                    continue
                yield {"type": "final", "content": "I wasn't able to find enough information to give a useful answer. Try rephrasing your request or starting a new session."}
                return

            if decision.get("thought"):
                yield {"type": "thought", "content": str(decision["thought"])}

            if "final_answer" in decision and "action" not in decision:
                if self._tools_used == 0 and self._corrections < 3:
                    self._corrections += 1
                    self.messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
                    self.messages.append({"role": "user", "content": "Do NOT answer from memory. Use a tool first — tool-call JSON now:\n{\"thought\":\"...\",\"action\":\"web_search\",\"action_input\":{\"query\":\"...\"}}"})
                    continue
                yield from self._grounded_final(str(decision["final_answer"]))
                return

            tool = decision.get("action")
            args = decision.get("action_input") or {}
            if not isinstance(args, dict):
                args = {}
            if not tool:
                yield {"type": "final", "content": "I wasn't able to process that request. Please try again or choose a suggested task."}
                return

            # Near step limit: force final answer instead of dispatching more tools.
            if self.steps >= MAX_STEPS - 1 and "final_answer" not in decision:
                self.messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
                self.messages.append({"role": "user", "content":
                    f"[LIMIT] No more tool calls — you are at {self.steps}/{MAX_STEPS}. "
                    "JSON final_answer NOW:\n"
                    "{\"thought\":\"...\",\"final_answer\":\"what I found or what went wrong\"}"})
                # Give the model one more inference to produce a final answer
                try:
                    final_raw = self.client.chat(self.messages, temperature=0.1, max_tokens=800)
                except LLMError:
                    final_raw = ""
                final_dec = _extract_json(final_raw)
                if final_dec and "final_answer" in final_dec:
                    yield from self._grounded_final(str(final_dec["final_answer"]))
                else:
                    yield {"type": "final", "content": "I wasn't able to find enough information to give a useful answer. Try rephrasing your request or starting a new session."}
                return

            yield {"type": "action", "tool": tool, "input": args}
            self._tools_used += 1
            self.messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})

            try:
                result = self._dispatch(tool, args)
            except Exception as exc:
                result = {"error": str(exc)}
            if isinstance(result, dict) and result.get("url"):
                self._last_page_url = result["url"]

            # Website login / credentials / final-submit hand-off.
            if isinstance(result, dict) and result.get("status") == "awaiting_user":
                if result.get("kind") == "credentials":
                    self._login_url = self._last_page_url
                    if self._use_saved_login(self._last_page_url):
                        self._do_login = False
                        yield from self._do_fill_login()
                        if self.awaiting:
                            return
                        continue
                self.awaiting = True
                self.messages.append({"role": "user", "content": f"[Paused] Waiting for the user: {result.get('reason')}."})
                ev = {"type": "awaiting_user", "reason": result.get("reason", "Please complete the step."),
                      "kind": result.get("kind", "login")}
                if result.get("fields"):
                    ev["fields"] = result["fields"]
                if result.get("details"):
                    ev["details"] = result["details"]
                yield ev
                return

            if isinstance(result, dict) and result.get("screenshot"):
                yield {"type": "screenshot", "url": result["screenshot"],
                       "page_url": result.get("url", ""), "title": result.get("title", "")}

            # Deterministic auto-login: if the page has a login form and we don't have
            # credentials yet, use a saved login if available, else surface the masked form.
            if (isinstance(result, dict) and result.get("has_login")
                    and not self._credentials and not self._login_requested):
                self._login_url = result.get("url") or self._last_page_url
                yield {"type": "observation", "tool": tool, "result": _trim(result)}
                if self._use_saved_login(self._login_url):
                    self._do_login = False
                    yield from self._do_fill_login()
                    if self.awaiting:
                        return
                    continue
                self._login_requested = True
                self.messages.append({"role": "user", "content":
                    f"Observation from {tool}: a login form was detected. The user is being asked for "
                    f"credentials in a secure form; once provided, call fill_login."})
                self.awaiting = True
                yield {"type": "awaiting_user",
                       "reason": "This page needs you to sign in. Enter your credentials and I'll log in for you.",
                       "kind": "credentials", "fields": ["username", "password"]}
                return

            trimmed = _trim(result)
            yield {"type": "observation", "tool": tool, "result": trimmed}
            note = _verify_note(tool, result)
            self.messages.append({"role": "user", "content":
                f"Observation from {tool}: {json.dumps(trimmed, ensure_ascii=False)}.{note}\n"
                f"Continue with the next JSON step."})

        yield {"type": "final", "content": "Reached the maximum number of steps without producing a final answer. The agent may have hit blocked pages or JS-rendered content."}

    def _do_fill_login(self) -> Iterator[dict[str, Any]]:
        yield {"type": "thought", "content": "Signing you in securely with the details you provided."}
        yield {"type": "action", "tool": "fill_login", "input": {"submit": True}}
        try:
            res = self._dispatch("fill_login", {"submit": True})
        except Exception as exc:
            res = {"error": str(exc)}
        self._tools_used += 1
        self.messages.append({"role": "assistant", "content": json.dumps(
            {"thought": "log in", "action": "fill_login", "action_input": {"submit": True}}, ensure_ascii=False)})
        if isinstance(res, dict) and res.get("screenshot"):
            yield {"type": "screenshot", "url": res["screenshot"],
                   "page_url": res.get("url", ""), "title": res.get("title", "")}
        trimmed = _trim(res)
        yield {"type": "observation", "tool": "fill_login", "result": trimmed}
        note = _verify_note("fill_login", res)
        self._post_login_url = res.get("url", "") if isinstance(res, dict) else ""
        self.messages.append({"role": "user", "content":
            f"Observation from fill_login: {json.dumps(trimmed, ensure_ascii=False)}.{note}\n"
            f"You are now signed in. Continue and complete the task — do not log in again."})

    def _extract_final(self, text: str) -> Iterator[dict[str, Any]]:
        """Write a grounded final answer from page text."""
        prompt = ("Based ONLY on the following page content, answer the user's original request. "
                  "Be factual and concise. Do NOT use any outside knowledge.\n\n"
                  f"Original request: {self._last_user}\n\n"
                  f"Page content:\n{text[:3000]}")
        try:
            answer = self.client.chat(
                [{"role": "system", "content": "You answer based only on the given text. Be concise."},
                 {"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=600)
        except LLMError:
            answer = "⚠️ The AI service isn't responding right now — please try again in a moment."
        yield {"type": "delta", "content": answer}
        yield {"type": "final", "content": answer}

    def _grounded_final(self, model_final: str) -> Iterator[dict[str, Any]]:
        """Generate a final answer grounded in actual tool calls, not model memory.

        The LLM tends to hallucinate what it *thinks* it filled when writing its own
        final_answer (e.g. saying "pizza" when it actually filled "cake"). This method
        extracts the actual tool-call arguments from the conversation and uses them as
        the sole source of truth.
        """
        # Collect actual tool calls from the assistant messages.
        actions_made: list[dict[str, Any]] = []
        for m in self.messages:
            if m["role"] == "assistant":
                try:
                    dec = json.loads(m["content"])
                    if dec.get("action") and dec.get("action_input"):
                        actions_made.append(dec)
                except (json.JSONDecodeError, TypeError):
                    pass

        if not actions_made:
            yield {"type": "delta", "content": model_final}
            yield {"type": "final", "content": model_final}
            return

        fact_lines: list[str] = ["Actions taken:"]
        for a in actions_made:
            tool = a.get("action", "")
            args = a.get("action_input", {})
            if tool == "fill_mark":
                fact_lines.append(f"  · Filled box #{args.get('n')} with: \"{args.get('text', '')}\"")
            elif tool == "fill_date":
                fact_lines.append(f"  · Filled date field #{args.get('n')} with: \"{args.get('text', '')}\"")
            elif tool == "fill_text_smart":
                fact_lines.append(f"  · Filled \"{args.get('value', '')}\" into field matching {args.get('synonyms', '')}")
            elif tool == "fill_date_smart":
                fact_lines.append(f"  · Filled date \"{args.get('value', '')}\" into field matching {args.get('synonyms', '')}")
            elif tool in ("submit_form", "click_smart"):
                fact_lines.append(f"  · {tool}()")
            elif tool == "click_mark":
                fact_lines.append(f"  · Clicked box #{args.get('n')}")
            elif tool == "fill_login":
                fact_lines.append("  · Filled login form with stored credentials")
            elif tool == "open_page":
                fact_lines.append(f"  · Navigated to: {args.get('url', '')}")
            elif tool == "web_search":
                fact_lines.append(f"  · Searched for: \"{args.get('query', '')}\"")
            elif tool == "arxiv_search":
                pid = args.get("paper_id", "")
                q = args.get("query", "")
                fact_lines.append(f"  · Searched arXiv: \"{q or pid}\"")
            elif tool == "save_document":
                fact_lines.append(f"  · Saved document: \"{args.get('filename', '')}\" ({len(args.get('content', ''))} chars)")
            elif tool == "read_page":
                fact_lines.append("  · Read current page content")
            elif tool == "see_page":
                fact_lines.append("  · Looked at current page visually (screenshot)")
            elif tool == "fill_field":
                fact_lines.append(f"  · Filled field \"{args.get('field', '')}\" = \"{args.get('value', '')}\"")
            elif tool == "click":
                fact_lines.append(f"  · Clicked: \"{args.get('target', '')}\"")

        facts = "\n".join(fact_lines)

        prompt = (
            "Based ONLY on the actual actions listed below, answer the user's request accurately.\n"
            "Use the EXACT field values shown in the actions — do NOT substitute or guess.\n"
            "If fields were filled, state exactly what value went where.\n\n"
            f"User request: {self._last_user}\n\n"
            f"{facts}\n\n"
            "Your concise answer:"
        )

        try:
            answer = self.client.chat(
                [{"role": "system", "content": "You give grounded answers based only on the provided data. Be precise and truthful."},
                 {"role": "user", "content": prompt}],
                temperature=0.05, max_tokens=400)
        except LLMError:
            # Fall back to the raw action log — no LLM needed, just the data
            answer = "Here's what I did:\n" + facts

        yield {"type": "delta", "content": answer}
        yield {"type": "final", "content": answer}

    def _stream_smalltalk(self) -> Iterator[dict[str, Any]]:
        """Answer a greeting / small-talk directly, no tool loop."""
        system = "You are Clark, a helpful autonomous web agent. Greet the user warmly."
        try:
            answer = self.client.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": self._last_user}],
                temperature=0.5, max_tokens=200)
        except LLMError:
            answer = "Hi! I'm Clark, your web agent. I'm ready when you are."
        yield {"type": "delta", "content": answer}
        yield {"type": "final", "content": answer}

    def _compact(self) -> None:
        """Keep context small — prune old observation messages."""
        if len(self.messages) <= 8:
            return
        total = sum(len(m.get("content", "")) for m in self.messages)
        if total < 8000:
            return
        system = self.messages[0]
        recent = self.messages[-6:] if len(self.messages) > 6 else self.messages[1:]
        self.messages = [system] + recent

    def _fit(self, max_chars: int) -> list[dict[str, str]]:
        """Trim messages to fit a model's context."""
        if not self.messages:
            return self.messages
        system, rest = self.messages[0], self.messages[1:]
        kept: list[dict[str, str]] = []
        total = len(system["content"])
        for m in reversed(rest):
            if total + len(m["content"]) > max_chars and kept:
                break
            kept.append(m)
            total += len(m["content"])
        kept.reverse()
        out = [system] + kept
        if total > max_chars and len(out) > 1:
            fixed = total - len(out[-1]["content"])
            allowed = max_chars - fixed
            if allowed > 120:
                out[-1] = {**out[-1], "content": out[-1]["content"][:allowed - 20] + " …[truncated]"}
        return out
