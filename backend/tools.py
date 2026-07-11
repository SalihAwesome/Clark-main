"""
Real agent tools for the Clark general-purpose web agent.

Unlike a mock chatbot, these tools take genuine actions:
  - web_search        : real web search (DuckDuckGo API via ddgs library)
  - open_page         : drives a REAL browser to a real URL (visible window)
  - read_page         : reads the visible text of the current page
  - see_page          : numbered overlay of every interactive element
  - click_mark        : click by numbered box
  - fill_mark         : type into a numbered box
  - fill_login        : auto-fill credentials (injected securely)
  - pause_for_user    : hands control to the human (OTP, captcha, submit)
  - save_document     : writes real artefacts to disk

Browser tools operate on a per-session real browser (see browser_session.py).
The session is injected by the agent loop — the model never sees it.

Safety model:
  * The agent NEVER types credentials. When login/OTP is needed, it calls
    request_credentials, the user types into a masked form, and the agent fills
    the form from there.
  * File writes are sandboxed under ./agent_workspace.
"""

from __future__ import annotations

import datetime
import inspect
import os
import pathlib
import re
from defusedxml import ElementTree as ET
from typing import Any, Callable

import httpx
from ddgs import DDGS

from browser_session import BrowserSession, get_session

WORKSPACE = pathlib.Path(os.getenv("AGENT_WORKSPACE", "agent_workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe_path(filename: str) -> pathlib.Path:
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).strip() or "untitled.txt"
    target = (WORKSPACE / name).resolve()
    if WORKSPACE not in target.parents and target != WORKSPACE:
        raise ValueError("Refusing to write outside the agent workspace.")
    return target


# --------------------------------------------------------------------------- #
# Web search (DuckDuckGo API via ddgs library)
# --------------------------------------------------------------------------- #
def web_search(query: str, max_results: int = 6) -> dict[str, Any]:
    """Search the web and return result titles + URLs + snippets."""
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        return {"query": query, "error": f"Search failed: {exc}", "results": []}

    results: list[dict[str, str]] = []
    for r in raw:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        })
    return {"query": query, "results": results, "count": len(results)}


# --------------------------------------------------------------------------- #
# arXiv search — abstracts via the API (way more reliable than scraping)
# --------------------------------------------------------------------------- #
def arxiv_search(query: str = "", paper_id: str = "", max_results: int = 3) -> dict[str, Any]:
    """Search arXiv papers or fetch a paper's full abstract by its arXiv ID.
    Either `query` (keyword search) or `paper_id` (like '2410.12412') must be set.

    Returns titles + full abstracts (no truncation). Use this INSTEAD of
    opening arXiv pages — those pages are truncated."""
    try:
        if paper_id:
            url = f"https://export.arxiv.org/api/query?id_list={paper_id}"
        else:
            q = httpx.URL(query.replace(" ", "+"))
            url = f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={max_results}"

        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}

        papers = []
        for entry in root.findall("a:entry", ns):
            title_el = entry.find("a:title", ns)
            summary_el = entry.find("a:summary", ns)
            id_el = entry.find("a:id", ns)
            papers.append({
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "abstract": (summary_el.text or "").strip() if summary_el is not None else "",
                "arxiv_id": (id_el.text or "").strip().split("/")[-1] if id_el is not None else "",
            })
        return {"papers": papers, "count": len(papers)}
    except Exception as exc:
        return {"error": f"arXiv search failed: {exc}", "papers": []}


# --------------------------------------------------------------------------- #
# Browser tools (operate on the injected session)
# --------------------------------------------------------------------------- #
def open_page(session: BrowserSession, url: str) -> dict[str, Any]:
    """Navigate the real browser to a URL and return the page state + screenshot."""
    return session.navigate(url)


def read_page(session: BrowserSession) -> dict[str, Any]:
    """Return the visible text + a fresh screenshot of the current page."""
    return session.state()


def list_form_fields(session: BrowserSession) -> dict[str, Any]:
    """List the visible form inputs on the current page so the agent can fill them."""
    return {"fields": session.list_inputs()}


def fill_field(session: BrowserSession, field: str, value: str) -> dict[str, Any]:
    """Type `value` into the input best matching `field` (name/id/placeholder/label)."""
    return session.fill(field, value)


def click(session: BrowserSession, target: str) -> dict[str, Any]:
    """Click a button / link / element matching `target` (visible text or selector)."""
    return session.click(target)


def see_page(session: BrowserSession) -> dict[str, Any]:
    """Set-of-Marks: draw numbered boxes over every clickable element and read the page."""
    return session.annotate()


def click_mark(session: BrowserSession, n: int) -> dict[str, Any]:
    """Click the numbered box from the most recent see_page (e.g. n=14)."""
    return session.click_mark(n)


def fill_mark(session: BrowserSession, n: int, text: str) -> dict[str, Any]:
    """Type into the numbered box from the most recent see_page."""
    return session.fill_mark(n, text)


def fill_date(session: BrowserSession, n: int, text: str = "", **kwargs: Any) -> dict[str, Any]:
    """Fill a DATE field by numbered box — robust to date-picker widgets and readonly
    date inputs. Accepts the format under `format` or `fmt` (default yyyy/mm/dd)."""
    fmt = kwargs.get("format") or kwargs.get("fmt") or "yyyy/mm/dd"
    return session.fill_date(int(n), text, fmt)


def fill_date_smart(session: BrowserSession, value: str = "", synonyms: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Fill a DATE by VALUE (no box number) — finds the field itself and handles a
    native date picker, a single text field, OR a 3-box year/month/day group."""
    if synonyms is None:
        synonyms = kwargs.get("synonym") or kwargs.get("labels") or []
    if isinstance(synonyms, str):
        synonyms = [synonyms]
    val = value or kwargs.get("text") or kwargs.get("date") or ""
    return session.fill_date_smart(str(val), list(synonyms or []))


def fill_text_smart(session: BrowserSession, value: str = "", synonyms: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Fill a TEXT field by MEANING (no box number) — finds the field by name/id/placeholder/label
    matching the synonyms, anywhere on the page, and sets it robustly."""
    if synonyms is None:
        synonyms = kwargs.get("synonym") or kwargs.get("labels") or []
    if isinstance(synonyms, str):
        synonyms = [synonyms]
    val = value or kwargs.get("text") or ""
    return session.fill_text_smart(str(val), list(synonyms or []))


def fill_login(session: BrowserSession, submit: bool = True,
               scope: str = "", humanize: bool = False) -> dict[str, Any]:
    """Fill the page's login form. The agent loop injects the user's credentials here;
    the model never sees the values."""
    return session.fill_login("", "", submit, scope, humanize)


def submit_form(session: BrowserSession) -> dict[str, Any]:
    """Press the page's Submit / Search / Inquire button."""
    return session.submit_form()


def click_smart(session: BrowserSession, labels: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Robustly click a navbar/header control — scrolls to the top first and
    matches by label (exact word or substring)."""
    if labels is None:
        labels = kwargs.get("label") or kwargs.get("target") or []
    if isinstance(labels, str):
        labels = [labels]
    return session.click_smart(list(labels or []))


def request_credentials(reason: str = "Please enter your login details.", fields: list[str] | None = None) -> dict[str, Any]:
    """Ask the user (securely, in the UI) for credentials to log in. Returns a control
    signal; the agent loop pauses and the user types them into a masked form."""
    return {"status": "awaiting_user", "kind": "credentials", "reason": reason, "fields": fields or ["username", "password"]}


def pause_for_user(reason: str) -> dict[str, Any]:
    """Hand control to the human (e.g. log in / enter OTP / confirm final submit).

    This returns a control signal; the agent loop stops and waits for the user to
    act in the real browser window and press Continue.
    """
    return {"status": "awaiting_user", "reason": reason}


# --------------------------------------------------------------------------- #
# Artefact tools (real file writes)
# --------------------------------------------------------------------------- #
def generate_official_letter(
    purpose: str,
    recipient: str,
    body: str,
    applicant_name: str = "",
) -> dict[str, Any]:
    """Generate a formatted official letter and save it to disk."""
    today = datetime.date.today().isoformat()
    text = (
        f"Date: {today}\nTo: {recipient}\n\nSubject: {purpose}\n\n"
        f"{body}\n\nYours sincerely,\n{applicant_name}\n"
    )
    fname = f"letter_{re.sub(r'[^A-Za-z0-9]+', '_', purpose)[:40] or 'official'}.txt"
    path = _safe_path(fname)
    path.write_text(text, encoding="utf-8")
    return {"saved_to": str(path.relative_to(WORKSPACE.parent)), "preview": text}


def save_document(filename: str, content: str) -> dict[str, Any]:
    """Write arbitrary text content to a file in the agent workspace."""
    path = _safe_path(filename)
    path.write_text(content, encoding="utf-8")
    return {"saved_to": str(path.relative_to(WORKSPACE.parent)), "bytes": len(content.encode("utf-8"))}


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
# Tools whose first argument is the browser session (injected by the agent loop).
_BROWSER_TOOLS = {"open_page", "read_page", "see_page", "click_mark", "fill_mark",
                  "fill_date", "fill_date_smart", "fill_text_smart", "fill_login",
                  "submit_form", "click_smart", "list_form_fields",
                  "fill_field", "click"}

TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "web_search": web_search,
    "arxiv_search": arxiv_search,
    "open_page": open_page,
    "read_page": read_page,
    "see_page": see_page,
    "click_mark": click_mark,
    "fill_mark": fill_mark,
    "fill_date": fill_date,
    "fill_date_smart": fill_date_smart,
    "fill_text_smart": fill_text_smart,
    "fill_login": fill_login,
    "submit_form": submit_form,
    "click_smart": click_smart,
    "request_credentials": request_credentials,
    "list_form_fields": list_form_fields,
    "fill_field": fill_field,
    "click": click,
    "pause_for_user": pause_for_user,
    "generate_official_letter": generate_official_letter,
    "save_document": save_document,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "web_search", "description": "Search the live web for information or to find the right URL. Use this first for general informational questions.", "args": {"query": "string"}},
    {"name": "arxiv_search", "description": "Fetch a research paper's full abstract from arXiv by paper_id (e.g. '2410.12412') or keyword query. Returns full text — NOT truncated. Use this INSTEAD of opening arXiv pages, which are truncated.", "args": {"paper_id": "string (optional) - arXiv ID like 2410.12412", "query": "string (optional) - keyword search", "max_results": "int (optional, default 3)"}},
    {"name": "open_page", "description": "Open a REAL browser at a URL (a visible window). Returns the page title, visible text, a screenshot, numbered interactive elements, a 'blocked' field if the site is blocking the browser, and a 'truncated' field if content is hidden behind a paywall/JS wall.", "args": {"url": "string"}},
    {"name": "see_page", "description": "PREFERRED way to interact: draws NUMBERED boxes over every clickable element on the current page and returns the labelled list, visible text, a 'blocked' field, and a 'truncated' field. Use this, then click_mark / fill_mark by number.", "args": {}},
    {"name": "click_mark", "description": "Click the numbered box from the most recent see_page (e.g. n=14).", "args": {"n": "int - the box number"}},
    {"name": "fill_mark", "description": "Type text into the numbered box (input) from the most recent see_page.", "args": {"n": "int - the box number", "text": "string"}},
    {"name": "fill_date", "description": "Fill a DATE field by its numbered box. Use this (not fill_mark) for any date/date-of-birth/expiry field — it handles date-picker calendar widgets and readonly date inputs. Pass the date and optionally its format.", "args": {"n": "int - the box number", "text": "string - the date, e.g. 1990/05/12", "format": "string (optional, default yyyy/mm/dd)"}},
    {"name": "fill_date_smart", "description": "Fill a DATE by VALUE without a box number — it finds the date field itself and handles ANY shape: a native date picker, a single text field, OR three separate year/month/day boxes or dropdowns. Prefer this for date fields.", "args": {"value": "string - the date, e.g. 1990/05/12", "synonyms": "list (optional) - words near the field, e.g. ['date of birth']"}},
    {"name": "fill_text_smart", "description": "Fill a TEXT field by MEANING (no box number) — finds the field by name/id/placeholder/label matching the synonyms.", "args": {"value": "string - the text to type", "synonyms": "list (optional) - words near the field, e.g. ['email']"}},
    {"name": "read_page", "description": "Re-read the current page's visible text and take a fresh screenshot. Returns a 'blocked' field if the site is blocking the browser, and a 'truncated' field if content is hidden behind a paywall/JS wall.", "args": {}},
    {"name": "request_credentials", "description": "Securely ask the user for login details. Use this when a page needs a login: the user types them into a MASKED form (you never see them). After this, call fill_login.", "args": {"reason": "string", "fields": "list (optional, default ['username','password'])"}},
    {"name": "fill_login", "description": "Auto-fill and submit the login form using the credentials the user just provided. You do NOT pass the values — they are injected securely.", "args": {"submit": "bool (optional, default true)"}},
    {"name": "submit_form", "description": "Press the page's Submit / Search / Inquire button.", "args": {}},
    {"name": "click_smart", "description": "Robustly click a navbar/header control (e.g. 'Sign In') — scrolls to the top first.", "args": {"labels": "list of text labels to match"}},
    {"name": "list_form_fields", "description": "List the form inputs on the current page (fallback to see_page).", "args": {}},
    {"name": "fill_field", "description": "Type a value into the input matching `field` (fallback to fill_mark).", "args": {"field": "string", "value": "string"}},
    {"name": "click", "description": "Click a button/link by visible text (fallback to click_mark).", "args": {"target": "string"}},
    {"name": "pause_for_user", "description": "Hand control to the human and WAIT (for OTP, captcha, payment, or a final irreversible submit).", "args": {"reason": "string"}},
    {"name": "generate_official_letter", "description": "Generate and SAVE a formatted official letter.", "args": {"purpose": "string", "recipient": "string", "body": "string", "applicant_name": "string (optional)"}},
    {"name": "save_document", "description": "Save any text content to a named file in the workspace.", "args": {"filename": "string", "content": "string"}},
]


# Common arg-name aliases the model sometimes emits. We only ever rename an
# alias to its canonical name when (a) the tool actually accepts the canonical name
# and (b) the canonical name is absent — so we never clobber a correct value.
_ARG_ALIASES: dict[str, tuple[str, ...]] = {
    "n": ("box", "index", "number", "mark", "box_number", "boxnumber", "boxnum", "i"),
    "text": ("value", "input", "content", "txt", "string"),
    "target": ("label", "selector", "element", "button", "link_text"),
    "url": ("link", "address", "href", "page", "site"),
    "query": ("q", "search", "search_query", "keyword", "keywords"),
    "field": ("field_name", "name_attr"),
}


def _prepare_args(fn: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """Make a model's tool call robust: map common arg-name aliases to the tool's
    real parameter names, drop anything the tool can't accept."""
    try:
        params = inspect.signature(fn).parameters
    except (ValueError, TypeError):
        return args
    names = set(params)
    out = dict(args)
    for canon, aliases in _ARG_ALIASES.items():
        if canon in names and canon not in out:
            for a in aliases:
                if a in out:
                    out[canon] = out.pop(a)
                    break
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return out
    allowed = {n for n, p in params.items()
               if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
    return {k: v for k, v in out.items() if k in allowed}


_accepted_args = _prepare_args


def run_tool(name: str, args: dict[str, Any], session_id: str | None = None,
             client: Any = None, surface: str = "web",
             credentials: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a tool call."""
    args = args or {}
    try:
        # Browser tools — inject a live per-session real browser.
        if name in _BROWSER_TOOLS:
            if not session_id:
                return {"error": "No browser session available for this tool."}
            # Securely inject the user's credentials into fill_login.
            if name == "fill_login":
                creds = credentials or {}
                args = {**args, "username": creds.get("username", ""), "password": creds.get("password", "")}
            fn = TOOLS[name]
            return fn(get_session(session_id, create=True), **_accepted_args(fn, args))

        # Plain tools (web_search, letter/document writers, pause_for_user, etc.).
        if name in TOOLS:
            fn = TOOLS[name]
            return fn(**_accepted_args(fn, args))

        return {"error": f"Unknown tool '{name}'."}
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:
        return {"error": f"Tool {name} failed: {exc}"}
