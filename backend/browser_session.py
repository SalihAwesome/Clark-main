"""
A persistent, real browser per agent session, driven by Playwright.

Playwright (vs Selenium) gives us the agent best-practices that modern computer-use
agents rely on:
  â€¢ Auto-waiting: clicks/fills wait for the element to be visible, enabled and stable
    before acting â€” no flaky time.sleep() guesses.
  â€¢ Fast, reliable navigation with explicit load states.
  â€¢ First-class locators and role/text queries.

Why a dedicated worker thread?
  Playwright's *sync* API objects are bound to the thread that created them, and the
  browser must survive across several HTTP requests (navigate â†’ the user logs in â†’
  resume). FastAPI serves our sync endpoints from a thread pool, so the browser can't
  live on a request thread. Each BrowserSession therefore owns ONE worker thread that
  holds the Playwright instance for its whole life; every browser operation is
  submitted to that thread as a closure and executed there.

Headful by default (a real visible window) so the human can complete login / OTP in
the same window. Set BROWSER_HEADLESS=true to run invisibly (tests).
Set BROWSER_LOCALE (default en-US) to control the page language.

Anti-bot: we launch a PERSISTENT Chrome profile (agent_workspace/chrome_profile, reused
across runs) plus a stealth init-script, so bot detection (e.g. reCAPTCHA) treats the
browser as a returning, reputable user rather than a throwaway automated session. Logins
on protected portals are typed human-like (real keystrokes + mouse movement) for the same
reason. Disable persistence with BROWSER_PERSISTENT=false; relocate with BROWSER_PROFILE_DIR.

Security: we never type credentials from the model. Login values are injected by the
agent loop from the user's securely-entered credentials.
"""

from __future__ import annotations

import base64
import os
import pathlib
import queue
import random
import re
import socket
import threading
from typing import Any, Callable

WORKSPACE = pathlib.Path(os.getenv("AGENT_WORKSPACE", "agent_workspace")).resolve()
SHOTS_DIR = WORKSPACE / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

_STOP = object()
_LOGIN_URL_HINTS = ("login", "signin", "sign-in", "logon", "/auth", "accounts.google", "/sso", "oauth")
_NEXT_WORDS = ["Next", "Sign in", "Log in", "Login", "Continue",
               "Ø§Ù„ØªØ§Ù„ÙŠ", "ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø¯Ø®ÙˆÙ„", "Ø¯Ø®ÙˆÙ„", "Ù…ØªØ§Ø¨Ø¹Ø©"]
# Words that label a "submit / search / inquire" button (EN + AR) â€” used so the agent can
# press the button ITSELF after filling a form (no more "please click Submit yourself").
_SUBMIT_WORDS = ["Search", "Submit", "Inquiry", "Inquire", "Enquire", "Verify", "Send Request",
                 "Ø¨Ø­Ø«", "Ø§Ø¨Ø­Ø«", "Ø¥Ø±Ø³Ø§Ù„", "Ø§Ø±Ø³Ø§Ù„", "ØªØ­Ù‚Ù‚", "Ø§Ø³ØªØ¹Ù„Ø§Ù…", "Ø¹Ø±Ø¶"]


class BrowserError(RuntimeError):
    pass


# Stealth: applied to every page before any site script runs, to defeat common
# headless/automation fingerprinting that bot detectors (incl. reCAPTCHA) score on:
# navigator.webdriver, the chrome object, plugins/mimeTypes, WebGL vendor/renderer,
# hardware specs, the permissions leak, and the headless-iframe contentWindow tell.
# CORE stealth â€” SAFE on ANY browser we launch (bundled Chromium AND real Chrome via channel=
# 'chrome'), because Playwright launches both as automated (navigator.webdriver=true, etc.).
# These only HIDE automation; they don't fake hardware, so they can't create a mismatch tell.
# (NOT applied when attached to the user's own Chrome over CDP â€” that browser isn't automated.)
_STEALTH_CORE_JS = r"""
(() => {
  const def = (obj, prop, get) => { try { Object.defineProperty(obj, prop, {get, configurable: true}); } catch (e) {} };

  // navigator.webdriver â€” the single biggest automation tell.
  def(navigator, 'webdriver', () => false);

  // A realistic window.chrome (real Chrome exposes runtime/app/csi/loadTimes).
  try {
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
    window.chrome.app = window.chrome.app || {isInstalled: false,
      InstallState: {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'},
      RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'}};
    if (!window.chrome.csi) window.chrome.csi = function () { return {}; };
    if (!window.chrome.loadTimes) window.chrome.loadTimes = function () { return {}; };
  } catch (e) {}

  // Languages.
  def(navigator, 'languages', () => ['en-US', 'en']);

  // The permissions.query leak (Notification.permission vs the real prompt state).
  try {
    const _q = window.navigator.permissions && window.navigator.permissions.query;
    if (_q) { window.navigator.permissions.query = (p) =>
      p && p.name === 'notifications'
        ? Promise.resolve({state: Notification.permission, onchange: null})
        : _q(p); }
  } catch (e) {}

  // An iframe's contentWindow can leak the automation flag â€” propagate the override.
  try {
    const desc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (desc && desc.get) {
      const get = desc.get;
      Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get() { const w = get.call(this); try { if (w) Object.defineProperty(w.navigator, 'webdriver', {get: () => false, configurable: true}); } catch (e) {} return w; },
        configurable: true,
      });
    }
  } catch (e) {}
})();
"""

# FINGERPRINT stealth â€” ONLY for BUNDLED Chromium, where the real values ARE tells (empty
# plugins, "SwiftShader/Mesa" WebGL, bare-VM hardware). We deliberately do NOT apply these on
# real Chrome (channel='chrome' or CDP): real Chrome already reports correct, self-consistent
# values, so faking them would CREATE a mismatch a bot-detector can catch.
_STEALTH_FINGERPRINT_JS = r"""
(() => {
  const def = (obj, prop, get) => { try { Object.defineProperty(obj, prop, {get, configurable: true}); } catch (e) {} };

  // Plugins + mimeTypes that look like a normal desktop Chrome with a PDF viewer
  // (an EMPTY plugins array is itself a headless tell).
  try {
    const mkPlugin = (name, filename, desc) => {
      const p = {name, filename, description: desc, length: 1};
      p.item = () => null; p.namedItem = () => null;
      return p;
    };
    const plugins = [
      mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
    ];
    plugins.item = (i) => plugins[i] || null;
    plugins.namedItem = (n) => plugins.find(p => p.name === n) || null;
    plugins.refresh = () => {};
    def(navigator, 'plugins', () => plugins);
    const mimes = [{type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'}];
    mimes.item = (i) => mimes[i] || null;
    mimes.namedItem = (n) => mimes.find(m => m.type === n) || null;
    def(navigator, 'mimeTypes', () => mimes);
  } catch (e) {}

  // Plausible hardware so the device doesn't look like a bare VM.
  def(navigator, 'hardwareConcurrency', () => 8);
  def(navigator, 'deviceMemory', () => 8);
  def(navigator, 'maxTouchPoints', () => 0);

  // WebGL vendor/renderer â€” headless Chromium reports "Google SwiftShader/Mesa"; spoof a real GPU.
  try {
    const spoof = (proto) => {
      const gp = proto.getParameter;
      proto.getParameter = function (p) {
        if (p === 37445) return 'Google Inc. (Intel)';                       // UNMASKED_VENDOR_WEBGL
        if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)'; // UNMASKED_RENDERER_WEBGL
        return gp.apply(this, [p]);
      };
    };
    if (window.WebGLRenderingContext) spoof(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) spoof(WebGL2RenderingContext.prototype);
  } catch (e) {}
})();
"""

# Error indicators on a page (EN + AR) â€” used to tell whether an action actually worked.
_ERROR_HINTS = ("error", "invalid", "incorrect", "not found", "try again", "failed",
                "wrong", "denied", "rejected", "Ø®Ø·Ø£", "ØºÙŠØ± ØµØ­ÙŠØ­", "ÙØ´Ù„", "Ø­Ø§ÙˆÙ„ Ù…Ø±Ø©")

# Bot-blocking / anti-scraping wall signals â€” when a page serves a captcha, "enable
# JavaScript" gate, or a truncated/spartan shell instead of real content, the agent needs
# to know it's BLOCKED, not that the page just happens to be empty.
_BOT_BLOCK_KEYWORDS = (
    "sorry", "robot", "automated access", "automated queries", "automated request",
    "captcha", "verify you're human", "verify your identity",
    "enable javascript", "javascript is required", "js is required",
    "your request has been blocked", "access denied", "access to this page",
    "please confirm you are a human", "unusual traffic",
    "something about your browser", "we need to make sure",
    "this site can't be reached", "not accessible",
)
# Minimum plausible body-text length for a real product/search/content page.
# Shorter likely means a bot wall, blank shell, or error page.
_MIN_CONTENT_LENGTH = 250


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Fast check whether something is listening (e.g. a debuggable Chrome on :9222), so CDP
    auto-detect costs ~0.4s when nothing is there instead of a long connect timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def _block_heavy(route) -> None:
    # Only used when BROWSER_FAST=true. Skip the heaviest assets (images/media) but
    # KEEP fonts and everything else so layout and scripts still work.
    try:
        if route.request.resource_type in ("image", "media"):
            route.abort()
        else:
            route.continue_()
    except Exception:  # noqa: BLE001
        try:
            route.continue_()
        except Exception:  # noqa: BLE001
            pass


class BrowserSession:
    def __init__(self, session_id: str, headless: bool | None = None) -> None:
        self.session_id = session_id
        if headless is None:
            headless = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
        self.headless = headless
        self.locale = os.getenv("BROWSER_LOCALE", "en-US")
        self.persistent = False     # set True when a persistent Chrome profile is in use
        self.profile_dir = ""       # the user-data-dir actually launched (for diagnostics)
        self.cdp = False            # set True when attached to the user's own Chrome over CDP
        self._real_chrome = False   # set True when using real Chrome (channel='chrome' or CDP)
        self._patchright = False    # set True when the patchright stealth fork is in use
        self._cmds: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._start_error: str | None = None
        self._shot_counter = 0
        self._last_live_shot: bytes = b""    # last good live frame (so polls never flash to blank)
        self._thread = threading.Thread(target=self._worker, name=f"browser-{session_id}", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=90):
            raise BrowserError("Browser did not start in time.")
        if self._start_error:
            raise BrowserError(self._start_error)

    # ------------------------------------------------------------------ #
    # Worker thread
    # ------------------------------------------------------------------ #
    def _worker(self) -> None:
        try:
            # patchright is a drop-in stealth fork of Playwright that closes the Runtime.enable /
            # main-world CDP leaks the in-page stealth script CANNOT reach (it only patches the
            # LAUNCH path, not connect_over_cdp). Use it when installed (pip install patchright);
            # otherwise fall back to stock Playwright with the same API.
            try:
                from patchright.sync_api import sync_playwright  # type: ignore
                self._patchright = True
            except Exception:  # noqa: BLE001
                from playwright.sync_api import sync_playwright
                self._patchright = False

            self._pw = sync_playwright().start()
            launch_kwargs = dict(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-first-run", "--no-default-browser-check",
                      "--disable-infobars", "--start-maximized",
                      # Keep the page RENDERING even when the window is minimized / not focused
                      # otherwise Windows occlusion detection suspends painting (screenshots freeze
                      # or go blank, and the window visibly repaints/"refreshes" when focus changes).
                      # With these, the agent can keep screenshotting + driving while you use the app.
                      "--disable-features=CalculateNativeWinOcclusion",
                      "--disable-backgrounding-occluded-windows",
                      "--disable-renderer-backgrounding",
                      "--disable-background-timer-throttling",
                      # Extra stealth: reduce automation fingerprints that bot-detection
                      # scripts (Amazon, Cloudflare, reCAPTCHA) score on.
                      "--disable-component-update",
                      "--disable-sync",
                      "--disable-client-side-phishing-detection"],
                ignore_default_args=["--enable-automation"],  # drop the "automation" banner/flag
            )
            base_context = dict(
                viewport={"width": 1280, "height": 860},
                locale=self.locale,
                bypass_csp=True,
            )
            # Only OVERRIDE the user-agent for BUNDLED Chromium (whose UA says "HeadlessChrome"/
            # "Chromium" â€” a tell). For REAL Chrome (channel='chrome') we let it send its OWN UA so
            # the UA, binary version and Client Hints stay self-consistent (a mismatch is itself a
            # tell). `channel` is None for bundled Chromium, 'chrome' for real Chrome.
            _BUNDLED_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            def ck_for(channel: str | None) -> dict[str, Any]:
                ck = dict(base_context)
                if not channel:
                    ck["user_agent"] = _BUNDLED_UA
                return ck

            self._browser = None
            self._ctx = None

            # STRONGEST anti-bot option: drive the user's OWN already-running Chrome over CDP.
            # That browser has a real fingerprint, history, extensions and (if the user is signed
            # into Google) a high reCAPTCHA reputation â€” so the score-based reCAPTCHA Enterprise on
            # portals like Tawtheeq passes where a freshly-automated browser is rejected. Start
            # Chrome with the bundled start-chrome-debug.bat (or:  chrome.exe
            # --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\clark-chrome"), sign into
            # Google once. We connect via BROWSER_CDP_URL, or AUTO-DETECT a debug Chrome on :9222
            # (disable auto-detect with BROWSER_CDP_AUTODETECT=false).
            cdp_url = os.getenv("BROWSER_CDP_URL", "").strip()
            if not cdp_url and os.getenv("BROWSER_CDP_AUTODETECT", "true").lower() != "false":
                if _port_open("127.0.0.1", 9222):     # a debuggable Chrome is already running â†’ use it
                    cdp_url = "http://127.0.0.1:9222"
            if cdp_url:
                try:
                    self._browser = self._pw.chromium.connect_over_cdp(cdp_url, timeout=8000)
                    # Reuse the user's real context (its cookies / Google login / history are the
                    # whole point); don't override its UA.
                    self._ctx = (self._browser.contexts[0] if self._browser.contexts
                                 else self._browser.new_context(**base_context))
                    self.cdp = True
                    self._real_chrome = True
                except Exception:  # noqa: BLE001 â€” Chrome not started with the debug port â†’ fall back
                    self._browser = None
                    self._ctx = None

            # A PERSISTENT profile is the next biggest anti-bot win: cookies, localStorage
            # and browsing history survive across runs, so reCAPTCHA (and similar) sees a
            # RETURNING, reputable browser instead of a fresh incognito session (which always
            # scores like a bot). It also means once a human passes a challenge ONCE in the
            # window, the trust cookie persists. Falls back to a per-session profile (if the
            # main one is already locked by another window) and finally to a plain context.
            # Disable with BROWSER_PERSISTENT=false; relocate with BROWSER_PROFILE_DIR.
            persistent = self._ctx is None and os.getenv("BROWSER_PERSISTENT", "true").lower() != "false"
            if persistent:
                # Headful and headless must NOT share a profile dir â€” mixing them corrupts the
                # profile and drops cookies (Playwright #35466), which would wreck reCAPTCHA
                # reputation. So the default dir is mode-specific.
                _suffix = "_headless" if self.headless else ""
                main_dir = os.getenv("BROWSER_PROFILE_DIR") or str(WORKSPACE / f"chrome_profile{_suffix}")
                for udd in (main_dir, str(WORKSPACE / f"chrome_profile_{self.session_id}")):
                    for channel in ("chrome", None):
                        kw = dict(launch_kwargs)
                        if channel:
                            kw["channel"] = channel
                        try:
                            pathlib.Path(udd).mkdir(parents=True, exist_ok=True)
                            self._ctx = self._pw.chromium.launch_persistent_context(udd, **kw, **ck_for(channel))
                            self.persistent = True
                            self.profile_dir = udd
                            self._real_chrome = bool(channel)
                            break
                        except Exception:  # noqa: BLE001 â€” locked profile / no Chrome channel â†’ try next
                            self._ctx = None
                    if self._ctx is not None:
                        break

            if self._ctx is None:
                # Non-persistent fallback: prefer real Chrome, else bundled Chromium.
                channel_used: str | None = None
                for channel in ("chrome", None):
                    kw = dict(launch_kwargs)
                    if channel:
                        kw["channel"] = channel
                    try:
                        self._browser = self._pw.chromium.launch(**kw)
                        channel_used = channel
                        break
                    except Exception:  # noqa: BLE001
                        self._browser = None
                if self._browser is None:
                    raise RuntimeError("Could not launch Chrome or bundled Chromium.")
                self._real_chrome = bool(channel_used)
                self._ctx = self._browser.new_context(**ck_for(channel_used))
            elif self._browser is None:
                self._browser = self._ctx.browser  # persistent context: may be None

            self._ctx.set_default_timeout(15000)
            # Stealth: NOT on CDP (the user's own Chrome isn't automated and is already consistent).
            # CORE (hide automation) on any browser we launch; the FINGERPRINT spoofs ONLY on
            # bundled Chromium (on real Chrome they'd create a mismatch tell â€” see the script docs).
            if not self.cdp:
                try:
                    self._ctx.add_init_script(_STEALTH_CORE_JS)
                    if not self._real_chrome:
                        self._ctx.add_init_script(_STEALTH_FINGERPRINT_JS)
                except Exception:  # noqa: BLE001
                    pass
            # By DEFAULT load the full page (images, fonts, media) exactly like a normal
            # browser, so real government sites render and behave correctly. Intercepting
            # every request (the old "fast" mode) both hid images and added big per-request
            # latency. Opt in with BROWSER_FAST=true only if you accept broken layout for speed.
            if os.getenv("BROWSER_FAST", "false").lower() == "true":
                self._ctx.route("**/*", _block_heavy)
            # For a CDP-attached real browser, open OUR OWN tab (don't hijack the user's tabs). A
            # launched persistent context starts with one blank page â€” reuse it (no 2nd window).
            if self.cdp:
                self._page = self._ctx.new_page()
            else:
                self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        except Exception as exc:  # noqa: BLE001
            self._start_error = (
                f"{exc}\n\nIf this is the first run, install the browser: "
                f"python -m playwright install chromium"
            )
            self._ready.set()
            return

        self._ready.set()
        while True:
            op, result_q = self._cmds.get()
            if op is _STOP:
                # When attached to the USER'S own Chrome over CDP, never close their browser or
                # context â€” just disconnect (pw.stop()). Otherwise close what we launched.
                if not self.cdp:
                    try:
                        self._ctx.close()
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        if self._browser:    # None for a persistent context
                            self._browser.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    self._pw.stop()
                except Exception:  # noqa: BLE001
                    pass
                result_q.put(("ok", None))
                return
            try:
                result_q.put(("ok", op(self)))
            except Exception as exc:  # noqa: BLE001
                result_q.put(("err", str(exc)))

    def _call(self, op: Callable[["BrowserSession"], Any], timeout: float = 120.0) -> Any:
        rq: "queue.Queue" = queue.Queue()
        self._cmds.put((op, rq))
        try:
            status, value = rq.get(timeout=timeout)
        except queue.Empty as exc:
            raise BrowserError("Browser operation timed out.") from exc
        if status == "err":
            raise BrowserError(str(value))
        return value

    # ------------------------------------------------------------------ #
    # Helpers (run INSIDE the worker thread)
    # ------------------------------------------------------------------ #
    def _save_shot(self) -> str:
        self._shot_counter += 1
        name = f"{self.session_id}_{self._shot_counter:03d}.png"
        try:
            self._page.screenshot(path=str(SHOTS_DIR / name), full_page=False)
        except Exception:  # noqa: BLE001
            return ""
        return name

    def _settle(self) -> None:
        # Make sure the DOM is ready, then wait only a SHORT moment for the network to
        # quiet down. We do NOT block on every image finishing â€” images keep streaming
        # into the visible browser in the background. The low cap avoids the old stall
        # where analytics/long-polling sites never reached 'networkidle' (a 4s hang).
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._page.wait_for_load_state("networkidle", timeout=1500)
        except Exception:  # noqa: BLE001
            pass

    def _clear_marks(self) -> None:
        try:
            self._page.evaluate("() => document.querySelectorAll('.__clark_mark').forEach(e => e.remove())")
        except Exception:  # noqa: BLE001
            pass

    def _human_mouse_to(self, x: float, y: float) -> None:
        """Move the mouse toward (x, y) in several small steps with a tiny pause â€” real pointer
        motion is a positive signal for behavioural bot scoring (reCAPTCHA v3 and friends)."""
        try:
            self._page.mouse.move(float(x), float(y), steps=random.randint(8, 22))
            self._page.wait_for_timeout(random.randint(40, 130))
        except Exception:  # noqa: BLE001
            pass

    def _human_type(self, selector: str, value: str) -> bool:
        """Type `value` into the tagged field like a human: move to it, click, then send REAL
        keystrokes with per-character delays (so the page sees keydown/keyup, not an instant
        value swap â€” the latter reads as a bot). Falls back to the native setter for SPA inputs
        that ignore synthetic key events. Returns True if the field was found."""
        if not value:
            return False
        try:
            loc = self._page.locator(selector).first
            if loc.count() == 0:
                return False
            try:
                loc.scroll_into_view_if_needed(timeout=2500)
            except Exception:  # noqa: BLE001
                pass
            box = _safe(lambda: loc.bounding_box(), None)
            if box:
                self._human_mouse_to(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            try:
                loc.click(timeout=3000)
            except Exception:  # noqa: BLE001
                pass
            self._page.wait_for_timeout(random.randint(70, 180))
            try:
                loc.fill("")
            except Exception:  # noqa: BLE001
                pass
            delay = random.randint(55, 145)
            try:
                loc.press_sequentially(value, delay=delay)
            except Exception:  # noqa: BLE001 â€” older Playwright spelling
                _safe(lambda: loc.type(value, delay=delay), None)
            # Verify it registered; if not, fall back to the native setter + events.
            if (_safe(lambda: loc.input_value(), "") or "") != value:
                _safe(lambda: self._page.evaluate(
                    "(a) => { const el = document.querySelector(a.sel); if (!el) return;"
                    " const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
                    " set.call(el, a.v); el.dispatchEvent(new Event('input', {bubbles: true}));"
                    " el.dispatchEvent(new Event('change', {bubbles: true})); }",
                    {"sel": selector, "v": value}), None)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _detect_error(self) -> str:
        """Return a short visible error/validation message if one is on the page, else ''."""
        page = self._page
        try:
            for el in page.query_selector_all(
                    "[role=alert], [aria-invalid='true'], .error, .alert-danger, .invalid-feedback, "
                    ".help-block, .field-error, .errorMessage"):
                if el.is_visible():
                    t = " ".join((el.inner_text() or "").split())
                    if t:
                        return t[:160]
            # Fallback: a short body that reads like an error.
            body = (page.evaluate("() => document.body ? document.body.innerText : ''") or "").lower()
            if len(body) < 600 and any(h in body for h in _ERROR_HINTS):
                return " ".join(body.split())[:160]
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _detect_login(self) -> bool:
        page = self._page
        try:
            url = (page.url or "").lower()
            has_pwd = any(e.is_visible() for e in page.query_selector_all("input[type=password]"))
            login_url = any(k in url for k in _LOGIN_URL_HINTS)
            has_user = any(e.is_visible() for e in page.query_selector_all(
                "input[type=email], input[type=text], input[id*='user'], input[id*='email'], "
                "input[name*='user'], input[name*='email']"))
            return has_pwd or (login_url and has_user)
        except Exception:  # noqa: BLE001
            return False

    def _detect_blocked(self, text: str) -> str:
        """Check if the page body suggests a bot-blocking wall.
        Returns a short reason string if blocked, '' otherwise."""
        if not text or len(text) < _MIN_CONTENT_LENGTH:
            low = text.lower()
            for kw in _BOT_BLOCK_KEYWORDS:
                if kw in low:
                    return f"page may be blocked — '{kw}' detected & content unusually short ({len(text)} chars)"
            if len(text) < 100:
                return f"page returned very little content ({len(text)} chars) — likely blocked or empty"
        return ""

    @staticmethod
    def _detect_truncated(text: str) -> str:
        """Check if the page content seems truncated (paywall, JS-only, cookie-wall).
        Returns a short reason string or '' if content looks fine."""
        if not text:
            return ""
        c = len(text)
        if c > 600:
            return ""  # enough text to be real content
        low = text.lower()
        # Pages with <600 chars that mention common paywall/cookie signals
        # and lack real content depth are likely truncated.
        paywall_signals = (
            "subscribe", "sign in", "sign in to read", "log in", "already a subscriber",
            "this article is", "become a member", "click to continue", "continue reading",
            "cookie", "privacy policy", "accept all", "reject all",
            "we value your privacy",
        )
        signal_count = sum(1 for s in paywall_signals if s in low)
        if signal_count >= 2 and c < 600:
            return f"page appears truncated/paywalled — content too short ({c} chars) with {signal_count} paywall signals"
        if c < 200:
            return f"page returned minimal content ({c} chars) — likely empty, error, or JS-only shell"
        return ""

    def _state(self) -> dict[str, Any]:
        page = self._page
        try:
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:  # noqa: BLE001
            text = ""
        text = " ".join((text or "").split())
        blocked = self._detect_blocked(text)
        truncated = self._detect_truncated(text) if not blocked else ""
        return {
            "url": page.url,
            "title": _safe(lambda: page.title()),
            "text": text[:4000],
            "screenshot": self._save_shot(),
            "has_login": self._detect_login(),
            "page_error": self._detect_error(),
            "blocked": blocked,
            "truncated": truncated,
        }

    def _annotated_state(self) -> dict[str, Any]:
        """Draw the numbered Set-of-Marks boxes, then return state WITH the element list.
        Used so every navigation/click leaves the page freshly labelled and ready to act on."""
        elements = _safe(lambda: self._page.evaluate(_ANNOTATE_JS), [])
        state = self._state()
        state["elements"] = elements
        return state

    def _visible(self, css: str):
        return [e for e in self._page.query_selector_all(css) if _safe(lambda: e.is_visible(), False)]

    def _submit_from(self, field) -> None:
        """Submit a login step reliably: press Enter in the field (works for most
        forms incl. Google's email/password steps); if we're still on the same page,
        fall back to clicking a Next/Sign-in button."""
        before = self._page.url
        try:
            field.press("Enter")
        except Exception:  # noqa: BLE001
            pass
        self._page.wait_for_timeout(1500)
        self._settle()
        if self._page.url == before and self._detect_login():
            self._click_next()
            self._page.wait_for_timeout(1500)
            self._settle()

    def _click_next(self) -> bool:
        page = self._page
        for w in _NEXT_WORDS:
            for getter in (
                lambda: page.get_by_role("button", name=w, exact=False),
                lambda: page.get_by_role("link", name=w, exact=False),
                lambda: page.get_by_text(w, exact=False),
            ):
                try:
                    loc = getter().first
                    if loc.is_visible():
                        loc.click(timeout=4000)
                        return True
                except Exception:  # noqa: BLE001
                    continue
        return False

    # ------------------------------------------------------------------ #
    # Public operations (callable from any thread)
    # ------------------------------------------------------------------ #
    def navigate(self, url: str) -> dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        def op(s: "BrowserSession") -> dict[str, Any]:
            try:
                s._page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:  # noqa: BLE001 (slow pages can still have usable content)
                if "Timeout" not in str(exc):
                    raise
            s._settle()
            # Auto-label the page so the agent can click_mark immediately, without a
            # separate see_page step (this was a real failure mode).
            return s._annotated_state()

        return self._call(op)

    def state(self) -> dict[str, Any]:
        return self._call(lambda s: s._state())

    # -- Set-of-Marks --------------------------------------------------- #
    def annotate(self) -> dict[str, Any]:
        return self._call(lambda s: s._annotated_state())

    def click_mark(self, n: int) -> dict[str, Any]:
        def op(s: "BrowserSession") -> dict[str, Any]:
            sel = f'[data-clark-mark="{int(n)}"]'
            before = (s._page.url, _safe(lambda: s._page.title()), len(s._page.content() or ""))
            try:
                s._page.locator(sel).first.click(timeout=5000)
            except Exception:  # noqa: BLE001 â€” marks may be stale/missing; re-label once and retry
                s._page.evaluate(_ANNOTATE_JS)
                s._page.locator(sel).first.click(timeout=5000)
            s._settle()
            # Re-label so the next step has fresh boxes (the page may have changed).
            st = s._annotated_state()
            after = (st.get("url"), st.get("title"), len(_safe(lambda: s._page.content(), "")))
            st["changed"] = (before[0] != after[0]) or (before[1] != after[1]) or abs(before[2] - after[2]) > 400
            return st

        return self._call(op)

    def fill_mark(self, n: int, text: str) -> dict[str, Any]:
        def op(s: "BrowserSession") -> dict[str, Any]:
            sel = f'[data-clark-mark="{int(n)}"]'
            try:
                s._page.locator(sel).first.fill(text, timeout=5000)
            except Exception:  # noqa: BLE001
                s._page.evaluate(_ANNOTATE_JS)
                s._page.locator(sel).first.fill(text, timeout=5000)
            # A typed value can pop a date-picker overlay; dismiss it so the next
            # click isn't swallowed by the calendar.
            try:
                s._page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                pass
            return {"filled_mark": n, **s._annotated_state()}

        return self._call(op)

    def fill_date(self, n: int, text: str, fmt: str = "yyyy/mm/dd") -> dict[str, Any]:
        """Fill a date field robustly â€” handles plain text inputs, native
        <input type=date>, JS date-picker widgets (incl. readonly ones), and
        React/framework-controlled inputs. `text` is the date in `fmt` order."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            sel = f'[data-clark-mark="{int(n)}"]'
            loc = s._page.locator(sel).first
            try:
                handle = loc.element_handle(timeout=5000)
            except Exception:  # noqa: BLE001 â€” marks may be stale; re-label and retry
                s._page.evaluate(_ANNOTATE_JS)
                loc = s._page.locator(sel).first
                handle = loc.element_handle(timeout=5000)

            input_type = (_safe(lambda: handle.get_attribute("type"), "") or "").lower()
            iso = _to_iso_date(text)           # yyyy-mm-dd for native date inputs
            typed = _format_date(text, fmt)    # what to TYPE into a text/picker field

            applied = ""
            # 1) Native HTML date input: must be yyyy-mm-dd.
            if input_type == "date" and iso:
                if not _safe(lambda: (loc.fill(iso, timeout=4000), True)[1], False):
                    s._set_value_js(handle, iso)
                applied = iso
            else:
                # 2) Text / date-picker field: try a real typed entry first.
                ok = _safe(lambda: (loc.fill(typed, timeout=4000), True)[1], False)
                if not ok or (loc.input_value() or "").strip() == "":
                    # 3) Readonly or framework-controlled: set value via the native
                    #    setter + fire input/change so React/Angular pick it up.
                    s._set_value_js(handle, typed)
                applied = typed

            # Close any open calendar overlay so it doesn't intercept later clicks.
            try:
                s._page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                pass
            s._page.wait_for_timeout(200)
            read_back = _safe(lambda: loc.input_value(), "")
            st = s._annotated_state()
            return {"filled_mark": n, "value_applied": applied, "field_value": read_back,
                    "input_type": input_type or "text", **st}

        return self._call(op)

    def _set_value_js(self, handle, value: str) -> None:
        """Set an input's value through the native setter and fire input/change/blur,
        so framework-controlled (React/Angular/Vue) and readonly fields accept it."""
        try:
            handle.evaluate(
                """(el, value) => {
                    const proto = el.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                    el.removeAttribute('readonly');
                    setter.call(el, value);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                }""",
                value,
            )
        except Exception:  # noqa: BLE001
            pass

    def fill_date_smart(self, value: str, synonyms: list[str] | None = None) -> dict[str, Any]:
        """Fill a date by VALUE (no box number) â€” robust to ANY date-input shape:
        a native <input type=date>, a single text/date-picker field, OR a 3-box
        year/month/day group (text inputs or <select> dropdowns, incl. month names).
        `synonyms` (e.g. ['date of birth','Ø§Ù„Ù…ÙŠÙ„Ø§Ø¯']) help locate the single field."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            p = _date_parts(value)
            if not p:
                return {"date_filled": False, "date_mode": "unparseable", **s._annotated_state()}
            y, m, d = p
            try:
                res = s._page.evaluate(_FILL_DATE_JS, {"y": y, "m": m, "d": d,
                                                       "syn": [str(x).lower() for x in (synonyms or [])]})
            except Exception as exc:  # noqa: BLE001
                res = {"filled": False, "mode": f"error: {exc}"}
            s._settle()
            try:
                s._page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                pass
            s._page.wait_for_timeout(150)
            st = s._annotated_state()
            return {"date_filled": bool(res.get("filled")), "date_mode": res.get("mode"),
                    "value": value, **st}

        return self._call(op)

    def fill_text_smart(self, value: str, synonyms: list[str] | None = None) -> dict[str, Any]:
        """Fill a TEXT input by MEANING (no box number) â€” robust where the box-numbered autofill
        fails: it scans the whole active scope (not just the viewport), matches the field by its
        name/id/placeholder/aria-label/associated-<label> against `synonyms` (e.g. ['qid','id number',
        'Ø§Ù„Ø±Ù‚Ù… Ø§Ù„Ø´Ø®ØµÙŠ']), SCROLLS to it, and sets the value via the native setter (so readonly /
        framework-controlled fields accept it). Skips captcha/search/password/OTP boxes. If nothing
        matches but the active form has exactly ONE fillable text input, it uses that."""
        syns = [str(x).lower() for x in (synonyms or []) if str(x).strip()]

        def op(s: "BrowserSession") -> dict[str, Any]:
            res = _safe(lambda: s._page.evaluate(_FILL_TEXT_JS, {"value": value, "syn": syns}), {}) or {}
            s._page.wait_for_timeout(120)
            st = s._annotated_state()
            return {"text_filled": bool(res.get("filled")), "matched": res.get("matched", ""),
                    "value": value, **st}

        return self._call(op)

    def fill_login(self, username: str = "", password: str = "", submit: bool = True,
                   scope: str = "", humanize: bool = False) -> dict[str, Any]:
        """Single-page AND multi-step (emailâ†’Nextâ†’password) logins. Values come from the
        user's securely-entered credentials; the model never sees them.

        Field selection is SEMANTIC, not DOM-order: we anchor on the password field, scope to
        its form, and pick the username field by login synonyms (skipping search/captcha boxes).
        `scope` (a CSS selector, e.g. '#login-method') restricts the search to a specific login
        container when the form isn't a <form> element. Values are set via the native setter +
        events so SPA (React/Angular) login forms actually register them. We capture a frame
        AFTER filling but BEFORE submit, so the user can SEE the fields populated; and if the
        login page also shows a captcha we DON'T blind-submit (the caller handles it).

        `humanize` (used on bot-protected portals like MOI E-Services / Tawtheeq) types the
        credentials with REAL keystrokes + mouse movement and pauses before submitting, so an
        invisible reCAPTCHA scores the session as a human instead of failing validation."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            if humanize:
                # Locate & TAG the fields without filling, then type them like a person.
                args = {"username": "", "password": "", "scope": scope or "", "tag_only": True}
                res = _safe(lambda: s._page.evaluate(_LOGIN_FILL_JS, args), {}) or {}
                if not res.get("has_password"):
                    s._page.wait_for_timeout(900)
                    s._settle()
                    res = _safe(lambda: s._page.evaluate(_LOGIN_FILL_JS, args), {}) or {}
                filled: list[str] = []
                if username and res.get("user_found"):
                    if s._human_type('[data-clark-login-user]', username):
                        filled.append("username")
                if password and res.get("has_password"):
                    s._page.wait_for_timeout(random.randint(120, 320))
                    if s._human_type('[data-clark-login-pass]', password):
                        filled.append("password")
            else:
                args = {"username": username, "password": password, "scope": scope or ""}
                res = _safe(lambda: s._page.evaluate(_LOGIN_FILL_JS, args), {}) or {}
                # The form can load a beat after the option is chosen â€” retry once if nothing took.
                if password and "password" not in (res.get("filled") or []):
                    s._page.wait_for_timeout(900)
                    s._settle()
                    res = _safe(lambda: s._page.evaluate(_LOGIN_FILL_JS, args), {}) or {}
                filled = res.get("filled", []) or []

            has_password = bool(res.get("has_password"))
            needs_captcha = bool(res.get("needs_captcha"))
            # Let the user SEE the populated fields before we submit/navigate away.
            pre_shot = s._save_shot()

            if has_password:
                if submit and not needs_captcha:
                    if humanize:
                        s._page.wait_for_timeout(random.randint(180, 420))  # human pause before submit
                    # Prefer the exact submit/Continue button we tagged (never a language toggle).
                    clicked = False
                    if res.get("submit_found"):
                        try:
                            loc = s._page.locator('[data-clark-login-submit]').first
                            if humanize:
                                box = _safe(lambda: loc.bounding_box(), None)
                                if box:
                                    s._human_mouse_to(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            loc.click(timeout=5000)
                            clicked = True
                        except Exception:  # noqa: BLE001
                            clicked = bool(_safe(lambda: s._page.evaluate(
                                "() => { const b = document.querySelector('[data-clark-login-submit]');"
                                " if (b) { b.click(); return true; } return false; }"), False))
                    if not clicked and not s._click_submit():
                        pw = s._visible("input[type=password]")
                        if pw:
                            s._submit_from(pw[0])
            elif username and "username" in filled:
                # Email-first step (Google-style): advance, then fill the password page.
                if not s._click_next():
                    try:
                        s._page.keyboard.press("Enter")
                    except Exception:  # noqa: BLE001
                        pass
                s._page.wait_for_timeout(2600)
                s._settle()
                res2 = _safe(lambda: s._page.evaluate(_LOGIN_FILL_JS,
                                                      {"username": "", "password": password}), {}) or {}
                if "password" in (res2.get("filled") or []):
                    filled.append("password")
                needs_captcha = needs_captcha or bool(res2.get("needs_captcha"))
                if submit and "password" in (res2.get("filled") or []) and not needs_captcha:
                    s._click_submit()

            s._settle()
            s._clear_marks()
            st = s._state()
            submitted = bool(submit) and not needs_captcha
            # Still on a login page (or an error showed) â†’ the login probably failed.
            st["login_succeeded"] = submitted and not st.get("has_login") and not st.get("page_error")
            return {"filled_fields": filled, "submitted": submitted, "needs_captcha": needs_captcha,
                    "username_field": res.get("user_id", ""), "pre_submit_frame": pre_shot, **st}

        return self._call(op)

    def submit_form(self) -> dict[str, Any]:
        """Press the page's Submit / Search / Inquire button OURSELVES (EN + AR), so the user
        never has to click it manually. Tries type=submit first (locale-independent), then the
        EN/AR submit words, then Enter in the last text field. Never raises."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            before = (s._page.url, _safe(lambda: s._page.title()), len(_safe(lambda: s._page.content(), "")))
            ok = s._click_submit()
            s._settle()
            st = s._annotated_state()
            after = (st.get("url"), st.get("title"), len(_safe(lambda: s._page.content(), "")))
            st["changed"] = (before[0] != after[0]) or (before[1] != after[1]) or abs(before[2] - after[2]) > 400
            st["submitted"] = bool(ok)
            return st

        return self._call(op)

    def submit_inquiry_form(self) -> dict[str, Any]:
        """Click the submit/search button INSIDE the form that holds the input fields (the
        inquiry form â€” preferring the one with the captcha box). Never the site-wide searchQuery
        form or any button outside the input form. Returns whether such a form/button was found."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            before = (s._page.url, _safe(lambda: s._page.title()), len(_safe(lambda: s._page.content(), "")))
            info = _safe(lambda: s._page.evaluate(_SUBMIT_IN_FORM_JS), {}) or {}
            clicked = False
            if info.get("found") and info.get("button"):
                try:
                    s._page.locator('[data-clark-submit]').first.click(timeout=5000)
                    clicked = True
                except Exception:  # noqa: BLE001 â€” fall back to a direct JS click on the tagged button
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-submit]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            st = s._annotated_state()
            after = (st.get("url"), st.get("title"), len(_safe(lambda: s._page.content(), "")))
            st["changed"] = (before[0] != after[0]) or (before[1] != after[1]) or abs(before[2] - after[2]) > 400
            st["submitted"] = clicked
            st["inquiry_form_found"] = bool(info.get("found"))
            st["inquiry_form"] = info.get("form", "")
            st["submit_label"] = info.get("label", "")
            return st

        return self._call(op)

    def detect_otp(self, field_selector: str = "#otp-field", form_selector: str = "#mfaOtpFrm",
                   timeout_ms: int = 6000) -> dict[str, Any]:
        """Wait briefly for a one-time-code (OTP) page to appear â€” the given field/form, or a
        generic OTP input. Returns {otp_present, selector}. Used to switch to the deterministic
        OTP step right after a multi-step (Tawtheeq) sign-in instead of leaving it to the model."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            waited, info = 0, {}
            while True:
                info = _safe(lambda: s._page.evaluate(
                    _OTP_DETECT_JS, {"field": field_selector or "", "form": form_selector or ""}), {}) or {}
                if info.get("found") or waited >= timeout_ms:
                    break
                s._page.wait_for_timeout(500)
                waited += 500
            return {"otp_present": bool(info.get("found")), "selector": info.get("selector", "")}

        return self._call(op)

    def fill_otp(self, code: str, field_selector: str = "#otp-field",
                 form_selector: str = "#mfaOtpFrm", humanize: bool = True) -> dict[str, Any]:
        """Type the one-time code into the OTP field (the given selector, else a generic OTP input)
        with REAL keystrokes, then click the Continue/submit button INSIDE the OTP form (never a
        language toggle or a 'Resend' link). The code comes from the user; the model never sees it."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            info = _safe(lambda: s._page.evaluate(
                _OTP_DETECT_JS, {"field": field_selector or "", "form": form_selector or ""}), {}) or {}
            sel = info.get("selector") or field_selector
            filled = False
            if sel and code:
                if humanize:
                    filled = s._human_type(sel, code)
                else:
                    filled = bool(_safe(lambda: s._page.evaluate(
                        "(a) => { const el = document.querySelector(a.sel); if (!el) return false;"
                        " const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
                        " d.call(el, a.v); el.dispatchEvent(new Event('input', {bubbles: true}));"
                        " el.dispatchEvent(new Event('change', {bubbles: true})); return true; }",
                        {"sel": sel, "v": code}), False))
            s._page.wait_for_timeout(random.randint(150, 350))   # brief human pause before submit
            sub = _safe(lambda: s._page.evaluate(_OTP_SUBMIT_JS, {"form": form_selector or ""}), {}) or {}
            clicked = False
            if sub.get("found"):
                try:
                    s._page.locator('[data-clark-otp-submit]').first.click(timeout=5000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-otp-submit]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            if not clicked:
                clicked = s._click_submit()
            s._settle()
            st = s._annotated_state()
            return {"otp_filled": bool(filled), "otp_submitted": bool(clicked),
                    "otp_field": sel, "submit_label": sub.get("label", ""), **st}

        return self._call(op)

    def fill_service_dialog(self, email: str = "", address_type: str = "Home Address",
                            language: str = "English", click_pay: bool = True) -> dict[str, Any]:
        """Fill the MOI service form that appears in a pop-up dialog (e.g. the National Address
        Certificate dialog): tick the address-type checkbox ("Home Address"), select the language
        ("English"), fill the email field with the user's email (injected by code â€” the model never
        types it, which is why it used to put a literal placeholder), and then press the PAY button
        to start the payment. Scoped to the topmost modal so it can't touch fields behind it."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            args = {"email": email or "", "address_type": address_type or "Home Address",
                    "language": language or "English", "click_pay": bool(click_pay)}
            res = _safe(lambda: s._page.evaluate(_FILL_SERVICE_DIALOG_JS, args), {}) or {}
            s._page.wait_for_timeout(300)   # let the form register the values before paying
            pay_clicked = False
            if click_pay and res.get("pay_found"):
                try:
                    s._page.locator('[data-clark-pay-btn]').first.click(timeout=5000)
                    pay_clicked = True
                except Exception:  # noqa: BLE001
                    pay_clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-pay-btn]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            st = s._annotated_state()
            return {"checkbox_set": bool(res.get("checkbox")), "language_set": bool(res.get("language")),
                    "email_set": bool(res.get("email")), "email_field": res.get("email_field", ""),
                    "pay_clicked": pay_clicked, "pay_label": res.get("pay_label", ""),
                    "scope": res.get("scope", ""), **st}

        return self._call(op)

    def read_payment_review(self) -> dict[str, Any]:
        """Extract the REVIEW PAYMENT page's details so we can SHOW them to the user before paying:
        the Total Fees and the Home Address label/value rows. Best-effort + a raw-text fallback."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            info = _safe(lambda: s._page.evaluate(_PAYMENT_REVIEW_JS), {}) or {}
            return {"total_fees": info.get("total_fees", ""), "address": info.get("address", []),
                    "title": info.get("title", ""), "raw": info.get("raw", ""),
                    "lines": info.get("lines", [])}

        return self._call(op)

    def expand_all(self, labels: list[str] | None = None) -> dict[str, Any]:
        """Click EVERY visible toggle whose text matches one of `labels` (e.g. "Show more info") to
        reveal hidden detail â€” used before reading the PHCC medications list (Dose/Frequency/Route
        are behind per-row "Show more info" links). Clicked toggles are tagged so re-passes don't
        collapse them; loops a few times because expanding one row can reveal more."""
        labels = [str(x) for x in (labels or []) if x]

        def op(s: "BrowserSession") -> dict[str, Any]:
            total = 0
            for _ in range(4):
                info = _safe(lambda: s._page.evaluate(_EXPAND_ALL_JS, {"labels": labels}), {}) or {}
                n = int(info.get("clicked", 0) or 0)
                total += n
                if n == 0:
                    break
                s._page.wait_for_timeout(350)
            s._settle()
            return {"expanded": total, **s._annotated_state()}

        return self._call(op)

    def confirm_payment_method(self, radio_id: str = "", card_label: str = "") -> dict[str, Any]:
        """In the MOI "Payment Method" dialog: tick the card-option radio (by id when known, e.g.
        '#qPayCardOptionRadio', else by Debit/Credit label) and click the dialog's "Pay" button,
        which redirects to the bank gateway. Operates directly on the DOM so it works even when the
        dialog isn't a recognised modal element (the old modal-detection missed it)."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            info = _safe(lambda: s._page.evaluate(_PAY_METHOD_JS,
                         {"radio_id": radio_id or "", "label": (card_label or "").lower()}), {}) or {}
            clicked = False
            if info.get("pay_found"):
                try:
                    s._page.locator('[data-clark-pay-btn]').first.click(timeout=4000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-pay-btn]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            return {"selected": bool(info.get("selected")), "radio_found": bool(info.get("radio_found")),
                    "pay_found": bool(info.get("pay_found")), "pay_clicked": clicked, **s._annotated_state()}

        return self._call(op)

    def fill_id_card_form(self, service_type: str = "") -> dict[str, Any]:
        """Replace Lost/Damaged ID Card â€” the "Expatriate Data" page: tick the Service Type radio
        ("Replace Lost"/"Replace Damaged" per `service_type`), tick the "My QID" radio, click Next,
        then confirm the delivery dialog ("OK"). Radios have no clickable text, so this selects them
        directly on the DOM by their labels â€” deterministic so the model can't skip them."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            info = _safe(lambda: s._page.evaluate(_FILL_ID_CARD_JS, {"service_type": service_type or ""}), {}) or {}
            next_clicked = False
            if info.get("next_found"):
                s._page.wait_for_timeout(200)
                try:
                    s._page.locator('[data-clark-next-btn]').first.click(timeout=4000)
                    next_clicked = True
                except Exception:  # noqa: BLE001
                    next_clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-next-btn]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            # Delivery confirmation dialog -> OK (it appears a beat after Next; wait for it).
            ok_clicked = False
            for _ in range(8):
                m = _safe(lambda: s._page.evaluate(_MODAL_CLICK_JS,
                          {"labels": ["OK", "Confirm", "Yes", "Continue"], "select": ""}), {}) or {}
                if m.get("found"):
                    try:
                        s._page.locator('[data-clark-modal-btn]').first.click(timeout=4000)
                        ok_clicked = True
                    except Exception:  # noqa: BLE001
                        ok_clicked = bool(_safe(lambda: s._page.evaluate(
                            "() => { const b = document.querySelector('[data-clark-modal-btn]');"
                            " if (b) { b.click(); return true; } return false; }"), False))
                    if ok_clicked:
                        break
                s._page.wait_for_timeout(400)
            s._settle()
            return {"service_set": bool(info.get("service_set")), "qid_set": bool(info.get("qid_set")),
                    "matched_service": info.get("matched_service", ""), "next_clicked": next_clicked,
                    "ok_clicked": ok_clicked, **s._annotated_state()}

        return self._call(op)

    def read_editable_form(self) -> dict[str, Any]:
        """Read the visible, editable fields of the form the user is changing (e.g. the National
        Address fields after pressing the first "Update"), so we can surface them IN THE APP for the
        user to review/change before writing them back. Returns {"fields":[{name,label,type,value,
        options}]}. Scans the topmost modal if one is open, else the whole document â€” and RETRIES a
        few times because fields can take a beat to become editable after the AJAX "Update" toggle."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            info: dict[str, Any] = {}
            for _ in range(4):
                s._page.wait_for_timeout(450)
                info = _safe(lambda: s._page.evaluate(_READ_EDITABLE_JS), {}) or {}
                if info.get("fields"):
                    break
            return {"fields": info.get("fields", []), "scope": info.get("scope", ""),
                    "count": info.get("count", 0)}

        return self._call(op)

    def fill_editable_form(self, values: dict[str, str]) -> dict[str, Any]:
        """Write the user's reviewed values back into the form fields (matched by name/id). Uses
        native setters + input/change events so SPA frameworks register the change."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            res = _safe(lambda: s._page.evaluate(_FILL_EDITABLE_JS, {"values": values or {}}), {}) or {}
            s._page.wait_for_timeout(150)
            return {"filled": res.get("filled", []), **s._annotated_state()}

        return self._call(op)

    def click_modal(self, labels: list[str] | None = None, timeout_ms: int = 6000,
                    select: str = "") -> dict[str, Any]:
        """In a POP-UP MODAL / dialog: optionally SELECT an option first (e.g. the 'Debit Card'
        radio in the payment dialog, via `select`), then click the primary action button (e.g.
        'Pay'/'Login'/'Continue'), preferring the modal footer. Waits up to `timeout_ms` for the
        modal. Never clicks Close/Cancel/Ã— or a language toggle."""
        labels = [str(x) for x in (labels or []) if x]

        def op(s: "BrowserSession") -> dict[str, Any]:
            waited, info = 0, {}
            while True:
                info = _safe(lambda: s._page.evaluate(_MODAL_CLICK_JS,
                             {"labels": labels, "select": select or ""}), {}) or {}
                if info.get("found") or waited >= timeout_ms:
                    break
                s._page.wait_for_timeout(500)
                waited += 500
            clicked = False
            if info.get("found"):
                try:
                    s._page.locator('[data-clark-modal-btn]').first.click(timeout=4000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-modal-btn]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            return {"modal_found": bool(info.get("modal")), "modal_clicked": clicked,
                    "option_set": bool(info.get("option_set")), "matched": info.get("text", ""),
                    **s._annotated_state()}

        return self._call(op)

    def click_smart(self, labels: list[str] | None = None) -> dict[str, Any]:
        """Robustly click a navbar/header control (e.g. the 'English' language link) â€” scroll to
        the TOP first so the navbar is rendered, match any of `labels` (exact word or substring),
        click it, then return the freshly-labelled page. Used for the language switch that the
        plain text-click sometimes can't locate."""
        labels = [str(x) for x in (labels or []) if x]

        def op(s: "BrowserSession") -> dict[str, Any]:
            try:
                s._page.evaluate("() => window.scrollTo(0, 0)")   # reveal the navbar
            except Exception:  # noqa: BLE001
                pass
            s._page.wait_for_timeout(200)
            info = _safe(lambda: s._page.evaluate(_SMART_CLICK_JS, {"labels": labels}), {}) or {}
            clicked = False
            if info.get("found"):
                try:
                    s._page.locator('[data-clark-smartclick]').first.click(timeout=4000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-smartclick]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            return {"clicked": clicked, "matched": info.get("text", ""), **s._annotated_state()}

        return self._call(op)

    def click_tab(self, labels: list[str] | None = None) -> dict[str, Any]:
        """Click a TAB / switch INSIDE the page body (e.g. the 'ID Number' tab that selects the
        search mode on the MOI fees page), as opposed to a navbar link. Prefers real tab controls
        ([role=tab], .nav-tabs, [data-toggle=tab], â€¦), matches a label (exact word or substring),
        scrolls it into view and clicks it â€” then returns the freshly-labelled page (clicking a tab
        usually swaps in a different set of input fields)."""
        labels = [str(x) for x in (labels or []) if x]

        def op(s: "BrowserSession") -> dict[str, Any]:
            info = _safe(lambda: s._page.evaluate(_CLICK_TAB_JS, {"labels": labels}), {}) or {}
            clicked = False
            if info.get("found"):
                try:
                    s._page.locator('[data-clark-tab]').first.click(timeout=4000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    clicked = bool(_safe(lambda: s._page.evaluate(
                        "() => { const b = document.querySelector('[data-clark-tab]');"
                        " if (b) { b.click(); return true; } return false; }"), False))
            s._settle()
            s._page.wait_for_timeout(250)   # let the tab's panel/fields render
            return {"clicked": clicked, "matched": info.get("text", ""), **s._annotated_state()}

        return self._call(op)

    def _click_submit(self) -> bool:
        """Find and click a submit/search button. Returns True if something was clicked."""
        page = self._page
        # 1) type=submit â€” the most reliable, language-independent signal.
        for css in ("button[type=submit]", "input[type=submit]", "input[type=image]"):
            try:
                loc = page.locator(css).first
                if loc.is_visible():
                    loc.click(timeout=4000)
                    return True
            except Exception:  # noqa: BLE001
                continue
        # 2) EN + AR submit/search words by role or visible text.
        for w in _SUBMIT_WORDS:
            for getter in (
                lambda w=w: page.get_by_role("button", name=w, exact=False),
                lambda w=w: page.get_by_role("link", name=w, exact=False),
                lambda w=w: page.get_by_text(w, exact=False),
            ):
                try:
                    loc = getter().first
                    if loc.is_visible():
                        loc.click(timeout=4000)
                        return True
                except Exception:  # noqa: BLE001
                    continue
        # 3) Last resort: press Enter in the last visible text field to submit the form.
        try:
            texts = self._visible("input[type=text], input[type=email], input[type=tel], input[type=password], input:not([type])")
            if texts:
                texts[-1].press("Enter")
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def fill_payment_card(self, card: dict[str, str]) -> dict[str, Any]:
        """Fill a payment/checkout form with the user's saved card (number, name, expiry, CVV)
        by matching field names/labels (EN + AR). Values are injected by code; the model never
        sees them. Handles a single MM/YY expiry field or split month/year fields."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            res = _safe(lambda: s._page.evaluate(_FILL_CARD_JS, {"card": card or {}}), {}) or {}
            s._page.wait_for_timeout(150)
            return {"card_filled": res.get("filled", []), **s._annotated_state()}

        return self._call(op)

    def capture_captcha(self) -> dict[str, Any]:
        """Locate the page's captcha image, screenshot just that region, and return it as a
        base64 data URL plus the Set-of-Marks numbers of the captcha INPUT box and the SUBMIT
        button â€” so the app can show the image, let the user type the code, and we fill + submit
        it ourselves. Degrades to {found: False} when no captcha image is recognisable."""
        def op(s: "BrowserSession") -> dict[str, Any]:
            s._page.evaluate(_ANNOTATE_JS)  # ensure inputs/buttons carry data-clark-mark
            info = _safe(lambda: s._page.evaluate(_CAPTCHA_JS), {}) or {}
            image = ""
            if info.get("found"):
                try:
                    png = s._page.locator('[data-clark-captcha-img]').first.screenshot(timeout=4000)
                    image = "data:image/png;base64," + base64.b64encode(png).decode()
                except Exception:  # noqa: BLE001 â€” fall back to a clip of the reported rect
                    rect = info.get("rect") or {}
                    try:
                        if rect.get("width", 0) > 4 and rect.get("height", 0) > 4:
                            png = s._page.screenshot(clip={"x": max(0, rect["x"]), "y": max(0, rect["y"]),
                                                           "width": rect["width"], "height": rect["height"]})
                            image = "data:image/png;base64," + base64.b64encode(png).decode()
                    except Exception:  # noqa: BLE001
                        image = ""
            return {"found": bool(info.get("found") and image), "image": image,
                    "input_mark": info.get("input_mark"), "submit_mark": info.get("submit_mark")}

        return self._call(op)

    # -- Fallback text/selector based ----------------------------------- #
    def list_inputs(self) -> list[dict[str, Any]]:
        def op(s: "BrowserSession") -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for el in s._page.query_selector_all("input, textarea, select"):
                try:
                    if not el.is_visible():
                        continue
                    out.append({
                        "tag": el.evaluate("e => e.tagName.toLowerCase()"),
                        "type": el.get_attribute("type") or "text",
                        "name": el.get_attribute("name") or "",
                        "id": el.get_attribute("id") or "",
                        "placeholder": el.get_attribute("placeholder") or "",
                        "label": el.get_attribute("aria-label") or "",
                    })
                except Exception:  # noqa: BLE001
                    continue
            return out[:40]

        return self._call(op)

    def fill(self, field: str, value: str) -> dict[str, Any]:
        target = (field or "").lower()

        def op(s: "BrowserSession") -> dict[str, Any]:
            for el in s._page.query_selector_all("input, textarea"):
                try:
                    if not el.is_visible():
                        continue
                    hay = " ".join(filter(None, [
                        el.get_attribute("name"), el.get_attribute("id"),
                        el.get_attribute("placeholder"), el.get_attribute("aria-label")])).lower()
                    if target and target in hay:
                        el.fill(value)
                        return {"filled": field, "value": value, **s._state()}
                except Exception:  # noqa: BLE001
                    continue
            raise BrowserError(f"No visible input matching '{field}'. Use see_page + fill_mark instead.")

        return self._call(op)

    def click(self, target: str) -> dict[str, Any]:
        def op(s: "BrowserSession") -> dict[str, Any]:
            page = s._page
            getters = [
                lambda: page.get_by_role("button", name=target, exact=False).first,
                lambda: page.get_by_role("link", name=target, exact=False).first,
                lambda: page.get_by_text(target, exact=False).first,
                # Image/logo "buttons" (e.g. the QPAY "NAPS" / "HIMYAN" card-network boxes): match the
                # logo by alt text or title and click it â€” the click bubbles to the selectable box.
                lambda: page.get_by_alt_text(target, exact=False).first,
                lambda: page.get_by_title(target, exact=False).first,
                lambda: page.get_by_role("img", name=target, exact=False).first,
                lambda: page.locator(target).first,
            ]
            # The model often passes an element's id/name (e.g. "payButton") as the target. The
            # text/role lookups miss it and `locator(target)` treats it as a tag â€” so also try it as
            # an id / name / partial-id selector.
            if target and re.match(r"^[A-Za-z][\w-]*$", target):
                t = target.replace('"', '')
                getters += [
                    lambda: page.locator(f'#{t}').first,
                    lambda: page.locator(f'[id="{t}"], [name="{t}"]').first,
                    lambda: page.locator(f'[id*="{t}" i], [name*="{t}" i]').first,
                ]
            for getter in getters:
                try:
                    loc = getter()
                    if loc.count() == 0:
                        continue
                    loc.click(timeout=4000)
                    s._settle()
                    return s._state()
                except Exception:  # noqa: BLE001
                    continue
            raise BrowserError(f"Could not find anything to click matching '{target}'.")

        return self._call(op)

    def live_screenshot(self) -> bytes:
        """Capture the CURRENT page (viewport only) as PNG bytes for the in-app live browser view
        that the UI polls. To stop the embedded view FLASHING to blank while the agent works (each
        poll during a navigation/redirect would otherwise time out and return nothing â†’ the UI fell
        back to the empty placeholder, which looked like the browser "refreshing"), we CACHE the last
        good frame and return it whenever a fresh capture isn't available."""
        def op(s: "BrowserSession") -> bytes:
            try:
                png = s._page.screenshot(full_page=False, timeout=4000)
                if png:
                    s._last_live_shot = png
                return png
            except Exception:  # noqa: BLE001 â€” mid-navigation / page closed â†’ reuse the last frame
                return s._last_live_shot
        try:
            return self._call(op) or self._last_live_shot
        except Exception:  # noqa: BLE001
            return self._last_live_shot

    def close(self) -> None:
        rq: "queue.Queue" = queue.Queue()
        self._cmds.put((_STOP, rq))
        try:
            rq.get(timeout=20)
        except queue.Empty:
            pass


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _date_parts(text: str) -> tuple[str, str, str] | None:
    """Best-effort parse of a date string into (year, month, day) as zero-padded
    strings. Accepts common separators (/ - .) and either yyyy-first or dd-first."""
    nums = re.findall(r"\d+", text or "")
    if len(nums) < 3:
        return None
    a, b, c = nums[0], nums[1], nums[2]
    if len(a) == 4:                     # yyyy m d
        y, m, d = a, b, c
    elif len(c) == 4:                   # d m yyyy  (or m d yyyy â€” assume d/m, common worldwide)
        d, m, y = a, b, c
    else:
        return None
    try:
        y, m, d = f"{int(y):04d}", f"{int(m):02d}", f"{int(d):02d}"
    except ValueError:
        return None
    return y, m, d


def _to_iso_date(text: str) -> str:
    """Convert a date string to yyyy-mm-dd (for native <input type=date>)."""
    p = _date_parts(text)
    return f"{p[0]}-{p[1]}-{p[2]}" if p else ""


def _format_date(text: str, fmt: str = "yyyy/mm/dd") -> str:
    """Render a date string in the requested display format (separator-aware).
    Falls back to the original text if it can't be parsed."""
    p = _date_parts(text)
    if not p:
        return text
    y, m, d = p
    sep = "/" if "/" in fmt else ("-" if "-" in fmt else ("." if "." in fmt else "/"))
    low = fmt.lower()
    order = (y, m, d) if low.find("y") < low.find("d") else (d, m, y)
    return sep.join(order)


# --------------------------------------------------------------------------- #
# Set-of-Marks annotation: draw a numbered box over every clickable element and
# tag it with data-clark-mark so we can click it by number.
# --------------------------------------------------------------------------- #
_ANNOTATE_JS = r"""
() => {
  document.querySelectorAll('.__clark_mark').forEach(e => e.remove());
  const sel = 'a, button, input, textarea, select, [role=button], [role=link], [role=checkbox], [role=tab], [role=menuitem], [onclick], summary, label';
  // If a blocking MODAL / dialog is open, only number controls INSIDE the topmost one. Otherwise
  // we'd number elements BEHIND the overlay (which intercepts every click), and the agent gets
  // stuck clicking covered fields â€” exactly the MOI "serviceModal" certificate-form failure.
  const _vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'
      && st.opacity !== '0' && el.getAttribute('aria-hidden') !== 'true'; };
  const modalSel = '.modal.in, .modal.show, .modal.open, [role=dialog][aria-modal="true"], ' +
                   '[role=alertdialog][aria-modal="true"], .ui-dialog, [class*=modal][class*=show], [class*=modal][class*=open]';
  let _modals = Array.from(document.querySelectorAll(modalSel)).filter(m =>
    _vis(m) && m.querySelector('a, button, input, select, textarea, [role=button], [onclick]'));
  _modals.sort((a, b) => ((parseInt(getComputedStyle(a).zIndex) || 0) - (parseInt(getComputedStyle(b).zIndex) || 0)));
  const scope = _modals.length ? _modals[_modals.length - 1] : document;
  const els = Array.from(scope.querySelectorAll(sel));
  const out = [];
  let i = 0;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    if (r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.pointerEvents === 'none') continue;
    i++;
    el.setAttribute('data-clark-mark', i);
    const label = (el.getAttribute('aria-label') || el.placeholder || el.name ||
                   (el.innerText || '').trim() || el.value || el.title || '').replace(/\s+/g, ' ').trim().slice(0, 50);
    out.push({ n: i, tag: el.tagName.toLowerCase(), type: el.type || '', label });
    const box = document.createElement('div');
    box.className = '__clark_mark';
    box.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;border:2px solid #4C8DFF;z-index:2147483646;pointer-events:none;box-sizing:border-box;`;
    const tag = document.createElement('div');
    tag.className = '__clark_mark';
    tag.textContent = i;
    tag.style.cssText = `position:fixed;left:${r.left}px;top:${Math.max(0, r.top - 15)}px;background:#4C8DFF;color:#04122B;font:bold 11px monospace;padding:0 4px;z-index:2147483647;pointer-events:none;`;
    document.body.appendChild(box);
    document.body.appendChild(tag);
  }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Smart TEXT filler (runs in the page): find a text input by meaning (synonyms vs
# name/id/placeholder/aria/label) ANYWHERE on the page, scroll to it, set value.
# --------------------------------------------------------------------------- #
_FILL_TEXT_JS = r"""
(args) => {
  const value = String(args.value == null ? '' : args.value);
  const syn = (args.syn || []).map(s => String(s).toLowerCase()).filter(Boolean);
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0'; };
  // Work inside the topmost open modal if there is one, else the whole document.
  const modalSel = '.modal.show, .modal.in, .modal[style*="display: block"], [role=dialog], .ui-dialog, [class*=modal][class*=show], [class*=modal][class*=open]';
  const modals = Array.from(document.querySelectorAll(modalSel)).filter(vis);
  const scope = modals.length ? modals[modals.length - 1] : document;
  const SKIP = /captcha|search|otp|one.?time|verification|verify|token|csrf|password|pass|pin|secret/i;
  const labelText = (el) => {
    let t = '';
    try { if (el.id) { const l = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    return t;
  };
  const hay = (el) => [el.getAttribute('name'), el.id, el.getAttribute('placeholder'),
    el.getAttribute('aria-label'), el.title, el.getAttribute('autocomplete'), labelText(el)]
    .filter(Boolean).join(' ').toLowerCase();
  const cands = Array.from(scope.querySelectorAll('input, textarea')).filter(el => {
    const ty = (el.getAttribute('type') || 'text').toLowerCase();
    if (['hidden','submit','button','reset','image','checkbox','radio','file','range','color','password'].includes(ty)) return false;
    if (!vis(el)) return false;
    if (SKIP.test(hay(el))) return false;
    return true;
  });
  let target = cands.find(el => syn.some(s => hay(el).includes(s)));
  if (!target && cands.length === 1) target = cands[0];   // single fillable field â†’ it's the one
  if (!target) return {filled: false, matched: ''};
  try { target.scrollIntoView({block: 'center'}); } catch (e) {}
  try { target.focus(); } catch (e) {}
  try {
    const proto = target.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    target.removeAttribute('readonly');
    setter.call(target, value);
    target.dispatchEvent(new Event('input', {bubbles: true}));
    target.dispatchEvent(new Event('change', {bubbles: true}));
    target.dispatchEvent(new Event('keyup', {bubbles: true}));
    target.dispatchEvent(new Event('blur', {bubbles: true}));
  } catch (e) { return {filled: false, matched: ''}; }
  return {filled: (target.value || '') === value, matched: (target.getAttribute('name') || target.id || hay(target)).slice(0, 40)};
}
"""


# --------------------------------------------------------------------------- #
# Universal date filler (runs in the page): native date input, a single text /
# date-picker field, or a 3-box year/month/day group (inputs or <select>s).
# --------------------------------------------------------------------------- #
_FILL_DATE_JS = r"""
(args) => {
  const y = args.y, m = args.m, d = args.d, syn = (args.syn || []).filter(Boolean);
  const MONTHS = ['january','february','march','april','may','june','july','august',
                  'september','october','november','december'];
  const AR_MONTHS = ['ÙŠÙ†Ø§ÙŠØ±','ÙØ¨Ø±Ø§ÙŠØ±','Ù…Ø§Ø±Ø³','Ø£Ø¨Ø±ÙŠÙ„','Ù…Ø§ÙŠÙˆ','ÙŠÙˆÙ†ÙŠÙˆ','ÙŠÙˆÙ„ÙŠÙˆ','Ø£ØºØ³Ø·Ø³',
                     'Ø³Ø¨ØªÙ…Ø¨Ø±','Ø£ÙƒØªÙˆØ¨Ø±','Ù†ÙˆÙÙ…Ø¨Ø±','Ø¯ÙŠØ³Ù…Ø¨Ø±'];
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype
      : (el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype);
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    try { el.removeAttribute('readonly'); } catch (e) {}
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const selectVal = (el, cands) => {
    for (const opt of Array.from(el.options)) {
      const ov = (opt.value || '').trim().toLowerCase();
      const ot = (opt.textContent || '').trim().toLowerCase();
      for (let c of cands) {
        c = String(c).toLowerCase();
        if (!c) continue;
        if (ov === c || ot === c || (c.length > 2 && ot.includes(c))) {
          el.value = opt.value;
          el.dispatchEvent(new Event('change', {bubbles: true}));
          return true;
        }
      }
    }
    return false;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const labelText = (el) => {
    let t = [el.getAttribute('aria-label'), el.getAttribute('placeholder'), el.name, el.id, el.title]
            .filter(Boolean).join(' ');
    try { if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    const ps = el.previousElementSibling; if (ps && ps.textContent) t += ' ' + ps.textContent;
    return t.toLowerCase().replace(/\s+/g, ' ');
  };
  const maxlen = (el) => { const v = parseInt(el.getAttribute('maxlength') || ''); return isNaN(v) ? 0 : v; };
  const numAttr = (el, n) => { const v = parseInt(el.getAttribute(n) || ''); return isNaN(v) ? null : v; };
  const inputs = Array.from(document.querySelectorAll('input, select, textarea')).filter(visible);

  // Classify a single box as 'year' | 'month' | 'day' | '' using label tokens, <select>
  // option patterns, and numeric attributes (maxlength / min / max / placeholder).
  const classify = (el) => {
    const t = labelText(el);
    if (/(^|[^a-z])(year|yyyy|Ø³Ù†Ø©|Ø¹Ø§Ù…)([^a-z]|$)/.test(t)) return 'year';
    if (/(^|[^a-z])(month|mm|Ø´Ù‡Ø±)([^a-z]|$)/.test(t)) return 'month';
    if (/(^|[^a-z])(day|dd|ÙŠÙˆÙ…)([^a-z]|$)/.test(t)) return 'day';
    if (el.tagName === 'SELECT') {
      const opts = Array.from(el.options).map(o => (o.textContent || '').trim().toLowerCase()).filter(Boolean);
      if (opts.some(o => MONTHS.includes(o) || AR_MONTHS.includes(o) || MONTHS.some(M => o.startsWith(M.slice(0, 3))))) return 'month';
      const nums = opts.map(o => parseInt(o)).filter(n => !isNaN(n));
      if (nums.length) { const mx = Math.max(...nums), mn = Math.min(...nums);
        if (mx >= 1900) return 'year';
        if (mx <= 12 && mn >= 1) return 'month';
        if (mx <= 31) return 'day'; }
    } else {
      const ml = maxlen(el), mx = numAttr(el, 'max');
      if (ml === 4 || (mx !== null && mx >= 1900)) return 'year';
      if ((ml === 1 || ml === 2) && mx !== null && mx <= 12) return 'month';
      if ((ml === 1 || ml === 2) && mx !== null && mx <= 31) return 'day';
    }
    return '';
  };
  const mi = parseInt(m);
  const put = (el, padded, plain, extra) => {
    if (el.tagName === 'SELECT') { if (!selectVal(el, [padded, plain].concat(extra || []))) selectVal(el, [plain]); }
    else setVal(el, padded);
  };
  const fillTrio = (yb, mb, db) => {
    put(yb, y, String(parseInt(y)));
    put(mb, m, String(parseInt(m)), [MONTHS[mi - 1] || '', (MONTHS[mi - 1] || '').slice(0, 3), AR_MONTHS[mi - 1] || '']);
    put(db, d, String(parseInt(d)));
  };

  // 1) native <input type=date>
  for (const el of inputs) {
    if (el.tagName === 'INPUT' && (el.type || '').toLowerCase() === 'date') {
      setVal(el, y + '-' + m + '-' + d); return {filled: true, mode: 'native'};
    }
  }

  // 2) SPLIT year/month/day group FIRST (so a shared group label can't trick branch 3
  //    into dumping the whole date into the first box). Classify by signals, not just tokens.
  let yb = null, mb = null, db = null;
  for (const el of inputs) {
    const c = classify(el);
    if (c === 'year' && !yb) yb = el;
    else if (c === 'month' && !mb) mb = el;
    else if (c === 'day' && !db) db = el;
  }
  if (yb && mb && db) { fillTrio(yb, mb, db); return {filled: true, mode: 'split'}; }

  // 2b) Heuristic split: three small numeric boxes (maxlength 1â€“4). If a synonym group of
  //     >=3 exists use it; else only act when there are EXACTLY three such boxes on the page.
  const small = inputs.filter(el => el.tagName === 'INPUT' && maxlen(el) >= 1 && maxlen(el) <= 4);
  const grp = small.filter(el => syn.some(s => labelText(el).includes(s)));
  let trio = grp.length >= 3 ? grp.slice(0, 3) : (small.length === 3 ? small : null);
  if (trio) {
    let yEl = trio.find(el => maxlen(el) === 4 || (numAttr(el, 'max') || 0) >= 1900);
    let rest = trio.filter(el => el !== yEl);
    if (!yEl) { yEl = trio[0]; rest = trio.slice(1); }
    let mEl = rest.find(el => { const mx = numAttr(el, 'max'); return mx !== null && mx <= 12; }) || rest[0];
    let dEl = rest.find(el => el !== mEl) || rest[1];
    if (yEl && mEl && dEl) { fillTrio(yEl, mEl, dEl); return {filled: true, mode: 'split-heuristic'}; }
  }

  // 3) single text / date-picker field matching the synonyms (must be able to hold a full date)
  for (const el of inputs) {
    if (el.tagName === 'SELECT') continue;
    const t = labelText(el);
    if (syn.some(s => t.includes(s))) {
      const ml = maxlen(el);
      if (ml && ml < 8) continue;        // too small for yyyy/mm/dd -> it's a sub-box, skip it
      setVal(el, y + '/' + m + '/' + d); return {filled: true, mode: 'single'};
    }
  }
  // 4) last resort: a date-ish single text field by placeholder/label
  for (const el of inputs) {
    if (el.tagName === 'SELECT') continue;
    const t = (el.getAttribute('placeholder') || '') + ' ' + labelText(el);
    if (/(date|ØªØ§Ø±ÙŠØ®|dd[\/\-.]mm|yyyy)/.test(t.toLowerCase())) {
      const ml = maxlen(el); if (ml && ml < 8) continue;
      setVal(el, y + '/' + m + '/' + d); return {filled: true, mode: 'single-fallback'};
    }
  }
  return {filled: false, mode: 'none'};
}
"""


# --------------------------------------------------------------------------- #
# Login form filler (runs in the page): picks the username field SEMANTICALLY,
# scoped to the password field's <form>, skipping search/captcha boxes, and sets
# values via the native setter so SPA (React/Angular) forms register them.
# --------------------------------------------------------------------------- #
_LOGIN_FILL_JS = r"""
(args) => {
  const U = args.username || '', P = args.password || '';
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const setVal = (el, v) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    try { el.removeAttribute('readonly'); } catch (e) {}
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new Event('blur', {bubbles: true}));
  };
  const attrs = (el) => [el.getAttribute('name'), el.id, el.getAttribute('placeholder'),
    el.getAttribute('aria-label'), el.getAttribute('autocomplete'), el.type].filter(Boolean).join(' ').toLowerCase();
  const out = {filled: [], needs_captcha: false};

  // Restrict the search to a specific login container (e.g. a <section id="login-method">)
  // when a scope selector is supplied and present; otherwise use the whole document.
  let root = document;
  if (args.scope) { try { const s = document.querySelector(args.scope); if (s) root = s; } catch (e) {} }

  const pwds = Array.from(root.querySelectorAll('input[type=password]')).filter(vis);
  out.has_password = pwds.length > 0;

  // captcha image present on the login page?
  out.needs_captcha = Array.from(root.querySelectorAll('img')).some(im =>
    /captcha|verif|securimage|Ø±Ù…Ø²|Ø§Ù„ØªØ­Ù‚Ù‚/i.test((im.src || '') + ' ' + (im.alt || '') + ' ' + (im.id || '') + ' ' + (im.className || '')));

  let scope = (pwds.length && pwds[0].form) ? pwds[0].form : root;
  let cands = Array.from(scope.querySelectorAll('input')).filter(el => vis(el)
    && !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'search'].includes((el.type || 'text').toLowerCase()));
  const searchy = (el) => /search|captcha|code|otp|Ø¨Ø­Ø«|Ø±Ù…Ø²/.test(attrs(el));
  let userCands = cands.filter(el => !searchy(el));
  if (!userCands.length) userCands = cands;

  const score = (el) => { const a = attrs(el); let s = 0;
    if ((el.type || '') === 'email') s += 5;
    if (/user|email|e-mail|login|account|sign/.test(a)) s += 4;
    if (/qid|national|civil|(^|[^a-z])id([^a-z]|$)|Ø§Ù„Ù‡ÙˆÙŠØ©|Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…|Ø§Ù„Ø¨Ø±ÙŠØ¯/.test(a)) s += 3;
    if ((el.type || 'text') === 'text') s += 1;
    return s; };

  let userEl = null;
  if (userCands.length) {
    const sorted = userCands.slice().sort((a, b) => score(b) - score(a));
    if (score(sorted[0]) > 0) userEl = sorted[0];
    else if (pwds.length) {
      // No semantic signal: take the text input immediately preceding the password field.
      const before = userCands.filter(el => el.compareDocumentPosition(pwds[0]) & Node.DOCUMENT_POSITION_FOLLOWING);
      userEl = before.length ? before[before.length - 1] : userCands[0];
    } else userEl = userCands[0];
  }

  // Tag the chosen fields so a human-like typer (Playwright keystrokes) can target them
  // exactly. When args.tag_only is set we ONLY tag (the caller types the values itself).
  try {
    document.querySelectorAll('[data-clark-login-user]').forEach(e => e.removeAttribute('data-clark-login-user'));
    document.querySelectorAll('[data-clark-login-pass]').forEach(e => e.removeAttribute('data-clark-login-pass'));
  } catch (e) {}
  if (userEl) {
    try { userEl.setAttribute('data-clark-login-user', '1'); } catch (e) {}
    out.user_found = true;
    out.user_id = userEl.id || userEl.getAttribute('name') || '';
    if (U && !args.tag_only) { setVal(userEl, ''); setVal(userEl, U); out.filled.push('username'); out.user_len = (userEl.value || '').length; }
  }
  if (pwds.length) {
    try { pwds[0].setAttribute('data-clark-login-pass', '1'); } catch (e) {}
    if (P && !args.tag_only) { setVal(pwds[0], P); out.filled.push('password'); out.pwd_len = (pwds[0].value || '').length; }
  }

  // Locate the form's SUBMIT/Continue button and tag it so Playwright can click exactly it â€”
  // never a language toggle (English/Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©), which is the bug we are fixing. Search the login
  // container first, then the document.
  try {
    document.querySelectorAll('[data-clark-login-submit]').forEach(e => e.removeAttribute('data-clark-login-submit'));
    const SUB_RE = /continue|next|log ?in|sign ?in|submit|proceed|Ù…ØªØ§Ø¨Ø¹Ø©|Ø§Ù„ØªØ§Ù„ÙŠ|ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø¯Ø®ÙˆÙ„|Ø¯Ø®ÙˆÙ„|Ø¥Ø±Ø³Ø§Ù„|ØªØ£ÙƒÙŠØ¯|Ø¯Ø®Ù€ÙˆÙ„/i;
    const LANG_RE = /english|arabic|Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©|Ø¹Ø±Ø¨ÙŠ|language|Ø§Ù„Ù„ØºØ©|\ben\b|\bar\b/i;
    const btnLabel = (b) => ((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.getAttribute('aria-label') || '') +
      ' ' + (b.id || '') + ' ' + (b.className || '') + ' ' + (b.title || '')).trim();
    const pickSubmit = (rootEl) => {
      const btns = Array.from(rootEl.querySelectorAll('button, input[type=submit], input[type=image], input[type=button], a[role=button], a'))
        .filter(vis).filter(b => (b.getAttribute('type') || '').toLowerCase() !== 'reset' && !LANG_RE.test(btnLabel(b)));
      return btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
          || btns.find(b => SUB_RE.test(btnLabel(b)))
          || (rootEl !== document ? (btns.find(b => b.tagName === 'BUTTON' && !(b.getAttribute('type') || '')) || null) : null);
    };
    const sb = pickSubmit(root) || pickSubmit(document);
    if (sb) { sb.setAttribute('data-clark-login-submit', '1'); out.submit_found = true; out.submit_label = btnLabel(sb).slice(0, 30); }
  } catch (e) {}
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Smart navbar/header click (runs in the page): find a control by label (exact
# word or substring), preferring the header/nav, tag + scroll it into view.
# --------------------------------------------------------------------------- #
_SMART_CLICK_JS = r"""
(args) => {
  const labels = (args.labels || []).map(s => String(s).toLowerCase().trim()).filter(Boolean);
  if (!labels.length) return {found: false};
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const txt = (el) => ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') +
    ' ' + (el.title || '') + ' ' + (el.value || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  document.querySelectorAll('[data-clark-smartclick]').forEach(e => e.removeAttribute('data-clark-smartclick'));
  const navSel = 'header a, header button, nav a, nav button, [class*=nav] a, [class*=nav] button, ' +
                 '[class*=header] a, [class*=header] button, [class*=lang] a, [class*=lang] button, ' +
                 '[id*=lang] a, [id*=lang] button';
  let cands = Array.from(document.querySelectorAll(navSel)).filter(vis);
  if (!cands.length) cands = Array.from(document.querySelectorAll('a, button, [role=button], input[type=button], input[type=submit]')).filter(vis);
  // Prefer an exact word/equality match, then a substring match.
  let el = cands.find(c => labels.some(l => txt(c) === l || txt(c).split(/\s+/).includes(l)));
  if (!el) el = cands.find(c => labels.some(l => l.length > 1 && txt(c).includes(l)));
  if (!el) return {found: false};
  el.setAttribute('data-clark-smartclick', '1');
  try { el.scrollIntoView({block: 'center'}); } catch (e) {}
  return {found: true, text: txt(el).slice(0, 40)};
}
"""


# --------------------------------------------------------------------------- #
# Tab/switch clicker (runs in the page): click a tab INSIDE the body (e.g. the
# "ID Number" search-mode tab on the MOI fees page), preferring real tab controls
# over arbitrary links. Does NOT touch the navbar. Tag + scroll the match into view.
# --------------------------------------------------------------------------- #
_CLICK_TAB_JS = r"""
(args) => {
  const labels = (args.labels || []).map(s => String(s).toLowerCase().trim()).filter(Boolean);
  if (!labels.length) return {found: false};
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const txt = (el) => ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') +
    ' ' + (el.title || '') + ' ' + (el.value || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  document.querySelectorAll('[data-clark-tab]').forEach(e => e.removeAttribute('data-clark-tab'));
  // Real tab controls first (Bootstrap / ARIA / common patterns), then any clickable element.
  const tabSel = '[role=tab], [data-toggle=tab], [data-bs-toggle=tab], [data-toggle=pill], ' +
                 '[data-bs-toggle=pill], .nav-tabs a, .nav-tabs button, .nav-tabs li, ' +
                 '.nav-pills a, .nav-pills button, ul.nav li a, .tab, .tabs a, .tabs button, ' +
                 '[class*=tab] a, [class*=tab] button, [class*=tab] li';
  let cands = Array.from(document.querySelectorAll(tabSel)).filter(vis);
  const generic = Array.from(document.querySelectorAll('a, button, [role=button], li, label, span')).filter(vis);
  if (!cands.length) cands = generic;
  const pick = (pool) => pool.find(c => labels.some(l => txt(c) === l || txt(c).split(/\s+/).includes(l)))
                      || pool.find(c => labels.some(l => l.length > 1 && txt(c).includes(l)));
  // Prefer a match among real tab controls; fall back to a generic clickable element.
  let el = pick(cands) || pick(generic);
  if (!el) return {found: false};
  const CLICKABLE = 'a, button, [role=tab], [role=button], [data-toggle], [data-bs-toggle], input';
  if (!el.matches(CLICKABLE)) {
    // Matched a container (<li>/<div>) or a deep inline node (<span>/<label>): use the real
    // clickable control â€” a descendant first (the <a> inside an <li>), else a clickable ancestor.
    const inner = el.querySelector(CLICKABLE);
    if (inner && vis(inner)) el = inner;
    else { const up = el.closest(CLICKABLE); if (up && vis(up)) el = up; }
  } else {
    // Already clickable, but if it's an inline child, hop to the nearest real control.
    const up = el.closest('a, button, [role=tab], [role=button], [data-toggle], [data-bs-toggle]');
    if (up && vis(up)) el = up;
  }
  el.setAttribute('data-clark-tab', '1');
  try { el.scrollIntoView({block: 'center'}); } catch (e) {}
  return {found: true, text: txt(el).slice(0, 40)};
}
"""


# --------------------------------------------------------------------------- #
# Payment-card filler (runs in the page): fill card number / name / expiry / CVV
# by matching field names/labels (EN + AR). Values are injected by code only.
# --------------------------------------------------------------------------- #
_FILL_CARD_JS = r"""
(args) => {
  const card = args.card || {};
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype
                : (el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype);
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    try { el.removeAttribute('readonly'); } catch (e) {}
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  // Haystack for a field: its own attributes PLUS its associated <label> text (QPAY labels the
  // Card Number / Expiry Month / Expiry Year fields only via <label>, not name/id/placeholder).
  const hay = (el) => {
    let t = [el.getAttribute('name'), el.id, el.getAttribute('placeholder'),
             el.getAttribute('aria-label'), el.getAttribute('autocomplete')].filter(Boolean).join(' ');
    try { if (el.id) { const l = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    if (clean(t).length < 3) { let p = el.previousElementSibling, hops = 0; while (p && hops < 2) { if (/^(label|span|div|td|th|p)$/i.test(p.tagName)) t += ' ' + (p.textContent || ''); p = p.previousElementSibling; hops++; } }
    return clean(t);
  };
  const fields = Array.from(document.querySelectorAll('input, select')).filter(vis);
  const used = new Set();
  const find = (syns) => fields.find(el => !used.has(el) && syns.some(s => hay(el).includes(s)));
  const out = {filled: []};
  let el;

  el = find(['card number', 'cardnumber', 'card_no', 'cardno', 'ccnumber', 'cc-number', 'pan', 'Ø±Ù‚Ù… Ø§Ù„Ø¨Ø·Ø§Ù‚Ø©']);
  if (el && card.card_number) { used.add(el); setVal(el, String(card.card_number)); out.filled.push('card_number'); }
  el = find(['cardholder', 'card holder', 'name on card', 'holdername', 'cc-name', 'ccname', 'Ø§Ø³Ù… Ø­Ø§Ù…Ù„']);
  if (el && card.cardholder_name) { used.add(el); setVal(el, String(card.cardholder_name)); out.filled.push('cardholder_name'); }

  // Expiry â€” a single MM/YY field, else split Month + Year that may be <select> dropdowns (QPAY).
  if (card.expiry) {
    const parts = String(card.expiry).split(/[\/\-\s.]+/).filter(Boolean);
    const mm = parts[0] || '', yy = parts[1] || '';
    const combined = find(['expiry date', 'expirydate', 'expiration date', 'exp-date', 'expdate', 'valid thru', 'cc-exp', 'mm/yy', 'mmyy']);
    if (combined && combined.tagName !== 'SELECT') { used.add(combined); setVal(combined, String(card.expiry)); out.filled.push('expiry'); }
    else {
      const MONTHS = ['january','february','march','april','may','june','july','august','september','october','november','december'];
      const setMonth = (sel, m) => {
        const n = parseInt(m, 10); if (!n || n < 1 || n > 12) return false;
        const cands = [String(n), ('0' + n).slice(-2), MONTHS[n - 1], MONTHS[n - 1].slice(0, 3)].map(x => x.toLowerCase());
        for (const o of sel.options) {
          const ov = o.value.trim().toLowerCase().replace(/^0+/, ''), ot = o.text.trim().toLowerCase().replace(/^0+/, '');
          if (cands.some(c => { const cc = c.replace(/^0+/, ''); return ov === cc || ot === cc || (cc.length > 2 && ot.startsWith(cc)); })) { setVal(sel, o.value); return true; }
        }
        return false;
      };
      const setYear = (sel, y) => {
        let n = parseInt(y, 10); if (!n) return false; const full = n < 100 ? 2000 + n : n;
        const cands = [String(full), String(full).slice(-2)];
        for (const o of sel.options) {
          const ov = o.value.trim(), ot = o.text.trim();
          if (cands.some(c => ov === c || ot === c || ov.endsWith(c) || ot.endsWith(c))) { setVal(sel, o.value); return true; }
        }
        return false;
      };
      const monthEl = find(['expiry month', 'expmonth', 'exp_month', 'exp-month', 'expirymonth', 'cardmonth', 'month', 'Ø´Ù‡Ø±']);
      if (monthEl && mm) { used.add(monthEl); const ok = monthEl.tagName === 'SELECT' ? setMonth(monthEl, mm) : (setVal(monthEl, mm), true); if (ok) out.filled.push('exp_month'); }
      const yearEl = find(['expiry year', 'expyear', 'exp_year', 'exp-year', 'expiryyear', 'cardyear', 'year', 'Ø³Ù†Ø©']);
      if (yearEl && yy) { used.add(yearEl); const ok = yearEl.tagName === 'SELECT' ? setYear(yearEl, yy) : (setVal(yearEl, yy), true); if (ok) out.filled.push('exp_year'); }
    }
  }

  el = find(['cvv', 'cvc', 'cvv2', 'cvc2', 'security code', 'securitycode', 'cc-csc', 'Ø±Ù…Ø² Ø§Ù„Ø£Ù…Ø§Ù†', 'Ø±Ù…Ø² Ø§Ù„ØªØ­Ù‚Ù‚']);
  if (el && card.cvv) { used.add(el); setVal(el, String(card.cvv)); out.filled.push('cvv'); }
  el = find(['zip', 'postal', 'postcode', 'post code', 'Ø§Ù„Ø±Ù…Ø² Ø§Ù„Ø¨Ø±ÙŠØ¯ÙŠ']);
  if (el && card.billing_zip) { used.add(el); setVal(el, String(card.billing_zip)); out.filled.push('billing_zip'); }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Captcha locator (runs in the page): find the captcha image (tag it for an
# element screenshot), the code INPUT box, and the SUBMIT button â€” returning the
# Set-of-Marks numbers so the agent can fill the user's code and submit itself.
# --------------------------------------------------------------------------- #
_CAPTCHA_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const re = /captcha|verif|securimage|Ø±Ù…Ø²|Ø§Ù„ØªØ­Ù‚Ù‚/i;
  const imgs = Array.from(document.querySelectorAll('img')).filter(vis);
  let cimg = imgs.find(im => re.test((im.src || '') + ' ' + (im.alt || '') + ' ' + (im.id || '') + ' ' + (im.className || '') + ' ' + (im.getAttribute('name') || '')));
  if (!cimg) cimg = imgs.find(im => /\.(aspx|php|jsp)|generateimage|getcaptcha|image\?|captchaimage/i.test(im.src || ''));
  document.querySelectorAll('[data-clark-captcha-img]').forEach(e => e.removeAttribute('data-clark-captcha-img'));
  const out = {found: false};
  if (!cimg) return out;
  cimg.setAttribute('data-clark-captcha-img', '1');
  out.found = true;
  const r = cimg.getBoundingClientRect();
  out.rect = {x: r.x, y: r.y, width: r.width, height: r.height};

  // captcha code input = nearest visible text input to the image (preferring captcha-named ones)
  const inputs = Array.from(document.querySelectorAll('input')).filter(el => vis(el)
    && !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password'].includes((el.type || 'text').toLowerCase()));
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  let best = null, bestD = 1e12;
  for (const el of inputs) {
    const er = el.getBoundingClientRect();
    let dd = Math.hypot(er.x + er.width / 2 - cx, er.y + er.height / 2 - cy);
    const a = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
    if (re.test(a) || /code/.test(a)) dd -= 600;     // strongly prefer a captcha/code-named box
    if (dd < bestD) { bestD = dd; best = el; }
  }
  if (best) { const mk = parseInt(best.getAttribute('data-clark-mark') || ''); if (!isNaN(mk)) out.input_mark = mk; }

  // submit/search button
  const btns = Array.from(document.querySelectorAll('button, input[type=submit], input[type=image], a[role=button], a')).filter(vis);
  const sre = /submit|search|verify|inquir|enquir|Ø¨Ø­Ø«|Ø§Ø¨Ø­Ø«|Ø¥Ø±Ø³Ø§Ù„|Ø§Ø±Ø³Ø§Ù„|ØªØ­Ù‚Ù‚|Ø§Ø³ØªØ¹Ù„Ø§Ù…/i;
  let sb = btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
       || btns.find(b => sre.test((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.id || '') + ' ' + (b.className || '') + ' ' + (b.getAttribute('aria-label') || '')));
  if (sb) { const mk = parseInt(sb.getAttribute('data-clark-mark') || ''); if (!isNaN(mk)) out.submit_mark = mk; }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Submit the INQUIRY form: find the <form> that holds the input fields (prefer the
# one containing the captcha box / the most filled inputs), then click the submit
# (a.k.a. search) button INSIDE THAT FORM ONLY â€” never the site-wide searchQuery
# form or any button outside the input form.
# --------------------------------------------------------------------------- #
_SUBMIT_IN_FORM_JS = r"""
() => {
  const SUBMIT_RE = /submit|search|inquir|enquir|Ø¨Ø­Ø«|Ø§Ø¨Ø­Ø«|Ø¥Ø±Ø³Ø§Ù„|Ø§Ø±Ø³Ø§Ù„|ØªØ­Ù‚Ù‚|Ø§Ø³ØªØ¹Ù„Ø§Ù…|Ø¹Ø±Ø¶/i;
  const RESET_RE  = /reset|clear|cancel|back|Ø¥Ù„ØºØ§Ø¡|Ù…Ø³Ø­|Ø§Ù„ØºØ§Ø¡|Ø±Ø¬ÙˆØ¹/i;
  // Forms to NEVER touch: the site-wide search form (often name/id 'searchQuery').
  const SEARCHFORM_RE = /search ?query|sitesearch|site-search|global ?search|header ?search|nav ?search|quick ?search/i;
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const formKey = (f) => ((f.getAttribute('name') || '') + ' ' + (f.id || '') + ' ' + (f.className || '')).toLowerCase();
  const isSearchForm = (f) => {
    const k = formKey(f);
    return SEARCHFORM_RE.test(k) || k.split(/[\s_-]+/).includes('search') || k.split(/[\s_-]+/).includes('searchquery');
  };
  const txtInputs = (f) => Array.from(f.querySelectorAll('input')).filter(el => vis(el) &&
    !['hidden', 'checkbox', 'radio', 'submit', 'button', 'image', 'search'].includes((el.type || 'text').toLowerCase()));
  const hasCaptcha = (f) => Array.from(f.querySelectorAll('input, img')).some(el =>
    /captcha|verif|Ø±Ù…Ø²|Ø§Ù„ØªØ­Ù‚Ù‚|code/i.test((el.name || '') + ' ' + (el.id || '') + ' ' +
      (el.getAttribute('placeholder') || '') + ' ' + (el.getAttribute('alt') || '') + ' ' + (el.className || '')));
  // A form is "live" only if it is actually VISIBLE. CRUCIAL for tabbed portals (e.g. the MOI
  // fees page has separate frmPlateNum / frmQid / frmCpy forms â€” only the active tab's form is
  // shown). Without this we'd submit a HIDDEN form's button (the wrong "Inquire") and nothing
  // happens. offsetParent is null for hidden (display:none) elements; also accept a form that
  // has at least one visible field (covers position:fixed layouts).
  const formVisible = (f) => (f.offsetParent !== null) ||
    Array.from(f.querySelectorAll('input, select, button')).some(vis);

  const forms = Array.from(document.querySelectorAll('form')).filter(f => !isSearchForm(f) && formVisible(f));
  // Prefer the visible form with the captcha box; else the visible form with the most filled inputs.
  let form = forms.find(hasCaptcha);
  if (!form) {
    let best = null, score = -1;
    for (const f of forms) {
      const ins = txtInputs(f);
      const filled = ins.filter(el => (el.value || '').trim().length > 0).length;
      const s = filled * 100 + ins.length;
      if (ins.length && s > score) { score = s; best = f; }
    }
    form = best;
  }
  if (!form) return {found: false};

  // The submit/search button INSIDE this form only.
  document.querySelectorAll('[data-clark-submit]').forEach(e => e.removeAttribute('data-clark-submit'));
  const label = (b) => ((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.getAttribute('aria-label') || '') +
    ' ' + (b.id || '') + ' ' + (b.className || '') + ' ' + (b.title || '')).trim();
  const btns = Array.from(form.querySelectorAll('button, input[type=submit], input[type=image], input[type=button], a[role=button], a'))
    .filter(vis).filter(b => (b.getAttribute('type') || '').toLowerCase() !== 'reset' && !RESET_RE.test(label(b)));
  const btn = btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
           || btns.find(b => SUBMIT_RE.test(label(b)))
           || btns.find(b => b.tagName === 'BUTTON' && !(b.getAttribute('type') || ''))
           || btns[0];
  if (!btn) return {found: true, form: formKey(form), button: false};
  btn.setAttribute('data-clark-submit', '1');
  return {found: true, form: formKey(form), button: true, label: label(btn).slice(0, 40)};
}
"""


# --------------------------------------------------------------------------- #
# OTP locator (runs in the page): find the one-time-code input â€” the explicit field
# selector (e.g. #otp-field), else a visible input inside the OTP form (e.g. #mfaOtpFrm),
# else a generic OTP/one-time-code input. Returns a usable CSS selector for it.
# --------------------------------------------------------------------------- #
_OTP_DETECT_JS = r"""
(args) => {
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const tag = (el) => { if (el.id) return '#' + el.id; el.setAttribute('data-clark-otp-input', '1'); return '[data-clark-otp-input]'; };
  const typable = (e) => !['hidden', 'submit', 'button', 'checkbox', 'radio'].includes((e.type || 'text').toLowerCase());
  // 1) explicit field selector
  if (args.field) { try { const el = document.querySelector(args.field); if (el && vis(el)) return {found: true, selector: args.field}; } catch (e) {} }
  // 2) a visible typable input inside the OTP form
  if (args.form) { try { const f = document.querySelector(args.form);
    if (f) { const inp = Array.from(f.querySelectorAll('input')).find(e => vis(e) && typable(e));
      if (inp) return {found: true, selector: tag(inp)}; } } catch (e) {} }
  // 3) a generic OTP / one-time-code input anywhere on the page
  const re = /otp|one.?time|verification|verify.?code|auth.?code|mfa|2fa|Ø±Ù…Ø²|Ø§Ù„ØªØ­Ù‚Ù‚/i;
  const g = Array.from(document.querySelectorAll('input')).filter(el => vis(el) && typable(el)).find(e =>
    e.getAttribute('autocomplete') === 'one-time-code' ||
    re.test((e.id || '') + ' ' + (e.name || '') + ' ' + (e.placeholder || '') + ' ' + (e.getAttribute('aria-label') || '')));
  if (g) return {found: true, selector: tag(g)};
  return {found: false};
}
"""


# OTP submit (runs in the page): click the Continue/Verify/submit button INSIDE the OTP form
# (scoped to args.form), never a language toggle, a Reset, or a "Resend code" link.
_OTP_SUBMIT_JS = r"""
(args) => {
  const root = (args.form && document.querySelector(args.form)) || document;
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const SUB  = /continue|next|submit|verify|confirm|log ?in|sign ?in|proceed|Ù…ØªØ§Ø¨Ø¹Ø©|Ø§Ù„ØªØ§Ù„ÙŠ|ØªØ£ÙƒÙŠØ¯|Ø¥Ø±Ø³Ø§Ù„|Ø¯Ø®ÙˆÙ„|ØªØ­Ù‚Ù‚/i;
  const LANG = /english|arabic|Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©|Ø¹Ø±Ø¨ÙŠ|language|Ø§Ù„Ù„ØºØ©|\ben\b|\bar\b/i;
  const SKIP = /reset|clear|cancel|back|resend|re-send|Ø¥Ù„ØºØ§Ø¡|Ù…Ø³Ø­|Ø±Ø¬ÙˆØ¹|Ø¥Ø¹Ø§Ø¯Ø©|Ø¥Ø¹Ø§Ø¯Ø© Ø¥Ø±Ø³Ø§Ù„/i;
  const label = (b) => ((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.getAttribute('aria-label') || '') +
    ' ' + (b.id || '') + ' ' + (b.className || '') + ' ' + (b.title || '')).trim();
  document.querySelectorAll('[data-clark-otp-submit]').forEach(e => e.removeAttribute('data-clark-otp-submit'));
  const btns = Array.from(root.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], a'))
    .filter(vis).filter(b => (b.getAttribute('type') || '').toLowerCase() !== 'reset' && !SKIP.test(label(b)) && !LANG.test(label(b)));
  const b = btns.find(x => (x.getAttribute('type') || '').toLowerCase() === 'submit')
         || btns.find(x => SUB.test(label(x)))
         || btns.find(x => x.tagName === 'BUTTON' && !(x.getAttribute('type') || ''))
         || btns[0];
  if (!b) return {found: false};
  b.setAttribute('data-clark-otp-submit', '1');
  return {found: true, label: label(b).slice(0, 30)};
}
"""


# Modal/dialog primary-action clicker (runs in the page): find the topmost VISIBLE modal/dialog
# and click its primary button (e.g. "Login"/"Continue") â€” footer first â€” never Close/Cancel/Ã—,
# never a language toggle, and never the option radios inside it (a default is already chosen).
_MODAL_CLICK_JS = r"""
(args) => {
  const labels = (args.labels || []).map(s => String(s).toLowerCase().trim()).filter(Boolean);
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0'
      && el.getAttribute('aria-hidden') !== 'true'; };
  const txt = (el) => ((el.innerText || el.textContent || '') + ' ' + (el.value || '') + ' ' +
    (el.getAttribute('aria-label') || '') + ' ' + (el.title || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  const modalSel = '.modal.show, .modal.in, .modal[style*="display: block"], [role=dialog], [role=alertdialog], ' +
                   '.ui-dialog, [class*=modal][class*=show], [class*=modal][class*=open], [class*=popup], [class*=dialog]';
  let modals = Array.from(document.querySelectorAll(modalSel)).filter(vis);
  if (!modals.length) return {found: false, modal: false};
  modals.sort((a, b) => ((parseInt(getComputedStyle(a).zIndex) || 0) - (parseInt(getComputedStyle(b).zIndex) || 0)));
  const modal = modals[modals.length - 1];   // topmost
  const out = {found: false, modal: true, option_set: false};

  // Optionally SELECT an option first (e.g. the "Debit Card" radio in the payment dialog).
  const select = String(args.select || '').toLowerCase().trim();
  if (select) {
    const labelOf = (el) => {
      let t = [el.getAttribute('aria-label'), el.id, el.getAttribute('name'), el.value].filter(Boolean).join(' ');
      try { if (el.id) { const l = modal.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
      const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
      const par = el.parentElement; if (par) t += ' ' + (par.textContent || '');
      return t.replace(/\s+/g, ' ').toLowerCase();
    };
    const opts = Array.from(modal.querySelectorAll('input[type=radio], input[type=checkbox]')).filter(vis);
    // Prefer an EXACT label, then a TIGHT match (label not much longer than the target â€” avoids
    // picking "Credit Card" when both radios share a parent whose text holds both labels), then loose.
    let o = opts.find(e => labelOf(e) === select)
         || opts.find(e => { const l = labelOf(e); return l.includes(select) && l.length <= select.length + 22; })
         || opts.find(e => labelOf(e).includes(select));
    if (o) {
      try { o.scrollIntoView({block: 'center'}); } catch (e) {}
      if (!o.checked) o.click();
      if (!o.checked) {   // framework-controlled inputs (React/Vue) can ignore .click() â€” force it
        try { o.checked = true;
              o.dispatchEvent(new Event('input', {bubbles: true}));
              o.dispatchEvent(new Event('change', {bubbles: true})); } catch (e) {}
      }
      out.option_set = o.checked;
    }
    if (!out.option_set) {   // a clickable option element (label/button/li/div) carrying the text
      const clk = Array.from(modal.querySelectorAll('label, button, a, [role=radio], [role=option], li, div')).filter(vis)
        .find(e => { const t = (e.innerText || '').trim().toLowerCase(); return t === select || (t.includes(select) && t.length < 40); });
      if (clk) { try { clk.scrollIntoView({block: 'center'}); } catch (e) {} clk.click(); out.option_set = true; }
    }
  }

  document.querySelectorAll('[data-clark-modal-btn]').forEach(e => e.removeAttribute('data-clark-modal-btn'));
  const SKIP = /close|cancel|dismiss|back|Ø¥ØºÙ„Ø§Ù‚|Ø¥Ù„ØºØ§Ø¡|Ø±Ø¬ÙˆØ¹|Ã—|âœ•|âœ–/i;
  const LANG = /english|arabic|Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©|Ø¹Ø±Ø¨ÙŠ|language|Ø§Ù„Ù„ØºØ©|\ben\b|\bar\b/i;
  const lbl = (b) => txt(b) + ' ' + (b.id || '').toLowerCase() + ' ' + (b.className || '').toLowerCase();
  const collect = (root) => Array.from(root.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], a'))
    .filter(vis).filter(b => (b.getAttribute('type') || '').toLowerCase() !== 'reset'
      && !LANG.test(lbl(b)) && !SKIP.test(txt(b)) && (txt(b).length > 0 || (b.value || '').length > 0));
  const footer = modal.querySelector('.modal-footer, .ui-dialog-buttonpane, [class*=footer], [class*=actions]');
  let cands = footer ? collect(footer) : [];
  if (!cands.length) cands = collect(modal);
  if (!cands.length) return out;
  let b = null;
  if (labels.length) {
    b = cands.find(c => labels.some(l => txt(c) === l || txt(c).split(/\s+/).includes(l)))
     || cands.find(c => labels.some(l => l.length > 1 && txt(c).includes(l)));
  }
  if (!b) b = cands.find(c => /btn-primary|\bprimary\b|submit|confirm/.test((c.className || '').toLowerCase()));
  if (!b) b = cands[cands.length - 1];   // last footer button is usually the primary/confirm action
  if (!b) return out;
  b.setAttribute('data-clark-modal-btn', '1');
  out.found = true; out.text = txt(b).slice(0, 40);
  return out;
}
"""


# Service-dialog filler (runs in the page): tick the address-type checkbox ("Home Address"),
# select the language ("English"), and fill the email field â€” all INSIDE the topmost modal so we
# never touch fields behind it. The email comes from the user's profile (injected by code).
_FILL_SERVICE_DIALOG_JS = r"""
(args) => {
  const email = String(args.email || '');
  const homeText = String(args.address_type || 'home address').toLowerCase();
  const langText = String(args.language || 'english').toLowerCase();
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none'
      && st.opacity !== '0' && el.getAttribute('aria-hidden') !== 'true'; };
  // Topmost open modal (else the whole document).
  const modalSel = '.modal.in, .modal.show, .modal.open, [role=dialog][aria-modal="true"], ' +
                   '[role=alertdialog][aria-modal="true"], .ui-dialog, [class*=modal][class*=show], [class*=modal][class*=open], ' +
                   '.modal[style*="display: block"], [role=dialog]:not([aria-hidden="true"])';
  let modals = Array.from(document.querySelectorAll(modalSel)).filter(m =>
    vis(m) && m.querySelector('input, select, button'));
  modals.sort((a, b) => ((parseInt(getComputedStyle(a).zIndex) || 0) - (parseInt(getComputedStyle(b).zIndex) || 0)));
  const scope = modals.length ? modals[modals.length - 1] : document;
  const scopeKey = modals.length ? ((scope.id || scope.className || 'modal') + '').slice(0, 40) : 'document';

  const labelOf = (el) => {
    let t = [el.getAttribute('aria-label'), el.id, el.getAttribute('name'), el.value, el.getAttribute('placeholder')].filter(Boolean).join(' ');
    try { if (el.id) { const l = scope.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    const par = el.parentElement; if (par) t += ' ' + (par.textContent || '');
    return t.replace(/\s+/g, ' ').toLowerCase();
  };
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    try { el.removeAttribute('readonly'); } catch (e) {}
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const out = {checkbox: false, language: false, email: false, email_field: '', scope: scopeKey};

  // 1) Address-type checkbox ("Home Address").
  const checks = Array.from(scope.querySelectorAll('input[type=checkbox]')).filter(vis);
  let cb = checks.find(c => labelOf(c).includes(homeText)) || (checks.length === 1 ? checks[0] : null);
  if (cb) { try { cb.scrollIntoView({block: 'center'}); } catch (e) {} if (!cb.checked) cb.click(); out.checkbox = cb.checked; }

  // 2) Language "English" â€” a radio, else a <select> option.
  const radios = Array.from(scope.querySelectorAll('input[type=radio]')).filter(vis);
  let lr = radios.find(r => labelOf(r).includes(langText));
  if (lr) { if (!lr.checked) lr.click(); out.language = lr.checked; }
  if (!out.language) {
    for (const sel of Array.from(scope.querySelectorAll('select')).filter(vis)) {
      const opt = Array.from(sel.options).find(o => (o.textContent || '').toLowerCase().includes(langText)
        || (o.value || '').toLowerCase().includes(langText));
      if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', {bubbles: true})); out.language = true; break; }
    }
  }

  // 3) Email field.
  if (email) {
    const inputs = Array.from(scope.querySelectorAll('input')).filter(vis);
    let em = inputs.find(el => (el.type || '').toLowerCase() === 'email')
          || inputs.find(el => /e-?mail|\bmail\b/i.test((el.id || '') + ' ' + (el.getAttribute('name') || '') + ' ' +
               (el.getAttribute('placeholder') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + labelOf(el)));
    if (em) { try { em.scrollIntoView({block: 'center'}); } catch (e) {} setVal(em, email);
              out.email = (em.value === email); out.email_field = em.id || em.getAttribute('name') || ''; }
  }

  // 4) Locate the PAY button so the caller can click it (the model kept passing the element id
  // "payButton" to the text-matching click tool and failing). Tag it; never a Cancel/Close/Reset.
  if (args.click_pay) {
    document.querySelectorAll('[data-clark-pay-btn]').forEach(e => e.removeAttribute('data-clark-pay-btn'));
    const SKIP = /reset|clear|cancel|back|close|dismiss/i;
    const textOf = (b) => ((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.title || '')).toLowerCase();
    const attrOf = (b) => ((b.id || '') + ' ' + (b.getAttribute('name') || '') + ' ' + (b.className || '')).toLowerCase();
    const btns = Array.from(scope.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], a'))
      .filter(vis).filter(b => (b.getAttribute('type') || '').toLowerCase() !== 'reset' && !SKIP.test(textOf(b)));
    let pb = btns.find(b => /\bpay\b|make payment|proceed.*pay|pay now/.test(textOf(b)))
          || btns.find(b => /(^|[^a-z])pay([^a-z]|$)|paybtn|paybutton|btnpay/.test(attrOf(b)))
          || btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
          || btns.find(b => /submit|continue|proceed/.test(textOf(b)));
    if (pb) { pb.setAttribute('data-clark-pay-btn', '1'); out.pay_found = true; out.pay_label = (textOf(pb) || attrOf(pb)).trim().slice(0, 40); }
  }
  return out;
}
"""


# Payment-review reader (runs in the page): pull the Total Fees and the Home Address label/value
# rows off the REVIEW PAYMENT page so the app can show them to the user before paying.
_PAYMENT_REVIEW_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const FEE_RE = /total\s*fee|fee\s*amount|total\s*amount|amount\s*(to\s*pay|due|payable)|service\s*fee|grand\s*total|Ø§Ù„Ø±Ø³ÙˆÙ…|Ø§Ù„Ù…Ø¨Ù„Øº|Ø§Ù„Ø¥Ø¬Ù…Ø§Ù„ÙŠ/i;
  const FIELD = /delivery|collection|collect|q-?post|courier|pickup|zone|street|building|unit|apartment|\bapt\b|flat|floor|electricity|phone|mobile|po ?box|p\.?\s*o\.?\s*box|\bcity\b|\barea\b|district|landmark|address|\bemail\b|\bname\b/i;
  // Button captions / chrome we must never treat as a label or value. (Anchored + word-boundary
  // so it only drops the exact caption, never a real label like "Home Address" or "Pay to".)
  const SKIP = /^(pay|continue|cancel|close|back|next|submit|confirm|ok|approve|proceed|dismiss|print)\s*$/i;

  // ---- 1) Choose the review REGION: the most specific visible container that holds a fee/total
  //      AND several address-ish fields. Smaller (more specific) wins on ties.
  let region = null, best = -1, bestLen = 1e9;
  const containers = Array.from(document.querySelectorAll('div, section, form, table, main, article, fieldset')).filter(vis);
  for (const c of containers) {
    const t = c.innerText || '';
    if (!t || t.length > 5000) continue;
    if (!FEE_RE.test(t)) continue;
    const fields = (t.match(new RegExp(FIELD.source, 'gi')) || []).length;
    const score = Math.min(fields, 14);
    if (score > best || (score === best && t.length < bestLen)) { best = score; bestLen = t.length; region = c; }
  }
  const scope = region || document.body || document.documentElement;

  // ---- 2) Collect the visible text in DOM ORDER, one label/value per line (input values inline).
  //      Newlines are preserved on purpose: the ordered sequence is what lets the model (and the
  //      positional fallback) pair each label with its CORRECT value, even when the page groups
  //      all labels together and then all values (which broke the old same-row heuristic).
  const lines = [];
  const push = (s) => {
    const v = clean(s);
    if (!v || v.length > 80) return;
    if (/^[\s:.\-â€“â€”|*/\\]+$/.test(v)) return;            // pure punctuation
    if (SKIP.test(v)) return;                              // a button caption
    if (lines.length && lines[lines.length - 1] === v) return;  // dedupe consecutive
    lines.push(v);
  };
  const walk = (node) => {
    if (!node || !vis(node)) return;
    const tag = node.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'BUTTON' || tag === 'A') return;
    if (tag === 'INPUT') {
      const ty = (node.getAttribute('type') || 'text').toLowerCase();
      if (['hidden', 'submit', 'button', 'reset', 'image', 'password', 'checkbox', 'radio'].includes(ty)) return;
      push(node.value); return;
    }
    if (tag === 'SELECT') { push(node.selectedOptions && node.selectedOptions[0] ? node.selectedOptions[0].text : node.value); return; }
    if (tag === 'TEXTAREA') { push(node.value); return; }
    if (node.children.length === 0) { push(node.textContent); return; }   // leaf element â†’ its text
    for (const ch of node.childNodes) {
      if (ch.nodeType === 3) push(ch.textContent);          // text directly under a mixed parent
      else if (ch.nodeType === 1) walk(ch);
    }
  };
  walk(scope);

  // ---- 3) DETERMINISTIC input-based pairing (PRIMARY) â€” the MOI review page is a Bootstrap
  //      horizontal form: each field is a `<label class="control-label">LABEL</label>` plus a
  //      sibling `<div><input disabled value=...></div>` inside one `.form-group`, and a "Q.R."
  //      unit label. Pair every value-holding input/select with its OWN label â†’ exact rows. (This
  //      is what the ordered-line/positional heuristic could never get right.)
  const UNIT = /^(q\.?\s*r\.?|qar|qr|ï·¼|Ø±\.?\s*Ù‚|riyals?|[:*]+)$/i;   // currency/punctuation labels, not a field name
  const labelOf = (el) => {
    let grp = el.closest('.form-group') || el.parentElement;       // climb form-groups (they nest)
    for (let i = 0; i < 4 && grp; i++) {
      const lab = Array.from(grp.querySelectorAll('label')).find(l => {
        const t = clean(l.textContent);
        return t && !UNIT.test(t) && !l.classList.contains('text-slim');
      });
      if (lab) return clean(lab.textContent);
      grp = grp.parentElement ? grp.parentElement.closest('.form-group') : null;
    }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    let p = el.previousElementSibling;                              // fallback: a preceding <label>
    while (p) { if (p.tagName === 'LABEL') { const t = clean(p.textContent); if (t && !UNIT.test(t)) return t; } p = p.previousElementSibling; }
    return '';
  };
  const valOf = (el) => clean(el.tagName === 'SELECT'
    ? (el.selectedOptions && el.selectedOptions[0] ? el.selectedOptions[0].text : el.value) : el.value);
  const holders = Array.from(scope.querySelectorAll('input, select, textarea')).filter(el => {
    if (!vis(el)) return false;
    const ty = (el.getAttribute('type') || 'text').toLowerCase();
    return !['hidden', 'submit', 'button', 'reset', 'image', 'password', 'checkbox', 'radio', 'file', 'search'].includes(ty);
  });
  const address = [], seen = {};
  let total = '';
  for (const el of holders) {
    const val = valOf(el);
    const lab = labelOf(el).replace(/[:*]+\s*$/, '').trim();
    if (!lab || UNIT.test(lab) || lab.length > 44) continue;
    const low = lab.toLowerCase();
    const nm = ((el.name || '') + ' ' + (el.id || '')).toLowerCase();
    if (/total\s*fee|grand\s*total|amount\s*payable|amount\s*due/.test(low) || /totalfee/.test(nm)) { if (val) total = val; continue; }
    if (!val || seen[low] || val.length > 80) continue;
    seen[low] = 1; address.push({label: lab, value: val});
    if (address.length >= 24) break;
  }

  // ---- 4) Total fee â€” prefer the labelled input; else a MONEY value near a fee label in `lines`.
  const MONEY_LINE = /^\s*(\d[\d,\s.]*)\s*(q\.?\s*r\.?|qar|qr|ï·¼|Ø±\.?\s*Ù‚|riyals?)?\s*$/i;
  if (!total) {
    for (let i = 0; i < lines.length; i++) {
      if (!FEE_RE.test(lines[i]) || /service\s*fee|delivery\s*fee/i.test(lines[i])) continue;
      const after = lines[i].replace(FEE_RE, '').replace(/[:*]+/g, '').trim();
      const mi = after.match(/\d[\d,\s.]*\s*(q\.?\s*r\.?|qar|qr|ï·¼|riyals?)?/i);
      if (mi && /\d/.test(mi[0])) { total = clean(mi[0]); break; }
      for (let j = i + 1; j < Math.min(i + 3, lines.length); j++) {
        if (MONEY_LINE.test(lines[j]) && /\d/.test(lines[j])) { total = clean(lines[j]); break; }
      }
      if (total) break;
    }
  }
  if (total && /^\s*[\d,.\s]+\s*$/.test(total)) total = clean(total) + ' QR';   // bare number â†’ add currency

  // ---- 5) Title.
  const titleLine = lines.find(l => /delivery\s*(option|detail|method|type)|home\s*address|address\s*detail|shipping/i.test(l) && l.length < 45);
  const title = titleLine ? (/delivery|shipping/i.test(titleLine) ? 'Delivery Options' : 'Home Address') : 'Details';

  // NOTE: no positional label/value fallback here on purpose â€” on a NOT-YET-POPULATED page it
  // pairs adjacent labels as garbage (Nameâ†’"RP Expiry Date"). When there are no labelled inputs
  // (a plain-text review page), `address` stays empty and the agent's model pairing handles it
  // from `lines` (which include any input values captured above).
  return {total_fees: total, address: address, title: title, lines: lines, raw: lines.join('\n').slice(0, 2500)};
}
"""


_EXPAND_ALL_JS = r"""
(args) => {
  const labels = (args.labels || []).map(s => String(s).toLowerCase().trim()).filter(Boolean);
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const txt = (el) => ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.title || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  const sel = 'a, button, [role=button], [onclick], summary, [aria-expanded], [class*=show-more], [class*=showmore], [class*=expand], [class*=toggle], [class*=more]';
  const els = Array.from(document.querySelectorAll(sel)).filter(vis);
  let clicked = 0;
  for (const el of els) {
    if (el.hasAttribute('data-clark-expanded')) continue;     // don't re-click (would collapse it)
    const t = txt(el);
    if (!t || t.length > 45) continue;
    if (!labels.some(l => t.includes(l))) continue;
    el.setAttribute('data-clark-expanded', '1');
    if (el.getAttribute('aria-expanded') === 'true') continue; // already open
    try { el.scrollIntoView({block: 'center'}); el.click(); clicked++; } catch (e) {}
  }
  return {clicked: clicked};
}
"""


_PAY_METHOD_JS = r"""
(args) => {
  const radioId = args.radio_id || '';
  const label = String(args.label || '').toLowerCase().trim();
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const labelOf = (el) => {
    let t = [el.getAttribute('aria-label'), el.id, el.getAttribute('name'), el.value].filter(Boolean).join(' ');
    try { if (el.id) { const l = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    const par = el.parentElement; if (par) t += ' ' + (par.textContent || '');
    return t.replace(/\s+/g, ' ').toLowerCase();
  };
  // Robustly select a radio (fires its inline onclick=selectQPayCardOption()/selectDebitCardOption()
  // exactly once; falls back to the label, then to a forced check, for styled/hidden radios).
  const check = (r) => {
    if (!r) return false;
    try { r.scrollIntoView({block: 'center'}); } catch (e) {}
    if (!r.checked) { try { r.click(); } catch (e) {} }
    if (!r.checked) { try { const l = r.id ? document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(r.id) : r.id) + '"]') : r.closest('label'); if (l) l.click(); } catch (e) {} }
    if (!r.checked) { try { r.checked = true; r.dispatchEvent(new Event('input', {bubbles: true})); r.dispatchEvent(new Event('change', {bubbles: true})); r.dispatchEvent(new Event('click', {bubbles: true})); } catch (e) {} }
    return !!r.checked;
  };
  // Find the card-option radio: by explicit id first (CREDIT=#debitCardOptionRadio,
  // DEBIT=#qPayCardOptionRadio), else by Debit/Credit label, else the first radio on the page.
  let radio = radioId ? document.getElementById(radioId) : null;
  if (!radio) {
    const radios = Array.from(document.querySelectorAll('input[type=radio], input[type=checkbox]'));
    radio = (label && radios.find(r => labelOf(r).includes(label))) || radios.find(r => vis(r)) || radios[0] || null;
  }
  const selected = check(radio);
  // Find the "Pay" button â€” prefer one inside the same dialog as the radio; never Close/Cancel.
  let scope = document;
  if (radio) { const m = radio.closest('.modal, [role=dialog], [role=alertdialog], .ui-dialog, [class*=modal], [class*=popup], [class*=dialog]'); if (m) scope = m; }
  document.querySelectorAll('[data-clark-pay-btn]').forEach(e => e.removeAttribute('data-clark-pay-btn'));
  const SKIP = /close|cancel|dismiss|back|Ø¥ØºÙ„Ø§Ù‚|Ø¥Ù„ØºØ§Ø¡|Ø±Ø¬ÙˆØ¹/i;
  const txt = (b) => ((b.innerText || b.textContent || '') + ' ' + (b.value || '')).replace(/\s+/g, ' ').trim();
  let btns = Array.from(scope.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]')).filter(vis).filter(b => !SKIP.test(txt(b)));
  if (!btns.length && scope !== document) btns = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]')).filter(vis).filter(b => !SKIP.test(txt(b)));
  let pay = btns.find(b => /^pay$/i.test(txt(b))) || btns.find(b => /\bpay\b/i.test(txt(b)))
         || btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit');
  if (pay) pay.setAttribute('data-clark-pay-btn', '1');
  return {selected: selected, radio_found: !!radio, pay_found: !!pay};
}
"""


_FILL_ID_CARD_JS = r"""
(args) => {
  const want = String(args.service_type || '').toLowerCase();
  const kw = want.includes('damage') ? 'damage' : (want.includes('lost') ? 'lost' : '');
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const labelOf = (el) => {
    let t = [el.getAttribute('aria-label'), el.id, el.getAttribute('name'), el.value].filter(Boolean).join(' ');
    try { if (el.id) { const l = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    const par = el.parentElement; if (par) t += ' ' + (par.textContent || '');
    let sib = el.nextSibling, hops = 0; while (sib && hops < 3) { if (sib.textContent) t += ' ' + sib.textContent; sib = sib.nextSibling; hops++; }
    return t.replace(/\s+/g, ' ').trim().toLowerCase();
  };
  // Robustly SELECT a radio even if it's visually hidden / custom-styled: click the input, then
  // its <label>, then force checked, dispatching events so the portal's JS registers the choice.
  const check = (r) => {
    if (!r) return false;
    try { r.scrollIntoView({block: 'center'}); } catch (e) {}
    try { if (!r.checked) r.click(); } catch (e) {}
    if (!r.checked) {
      try { const l = r.id ? document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(r.id) : r.id) + '"]') : r.closest('label'); if (l) l.click(); } catch (e) {}
    }
    if (!r.checked) { try { r.checked = true; } catch (e) {} }
    try { r.dispatchEvent(new Event('input', {bubbles: true})); r.dispatchEvent(new Event('change', {bubbles: true})); r.dispatchEvent(new Event('click', {bubbles: true})); } catch (e) {}
    return !!r.checked;
  };
  const byId = (id) => document.getElementById(id);
  const radios = Array.from(document.querySelectorAll('input[type=radio]'));   // do NOT pre-filter on vis: real radios are often hidden behind styled labels
  const out = {service_set: false, qid_set: false, next_found: false, matched_service: ''};

  // Service Type â€” prefer the KNOWN MOI ids, else match by label ("lost"/"damaged").
  let svc = null;
  if (kw === 'damage') svc = byId('radio_service_damaged');
  else if (kw === 'lost') svc = byId('radio_service_lost');
  if (!svc && kw) svc = radios.find(x => labelOf(x).includes(kw));
  if (svc) { out.service_set = check(svc); out.matched_service = (svc.id || labelOf(svc)).slice(0, 30); }

  // QID Options â€” "My QID" by KNOWN id, else by label (never the family-member/expatriate one).
  let q = byId('radio_service_qid');
  if (!q) q = radios.find(x => { const l = labelOf(x);
    return l.includes('my qid') || (l.includes('qid') && !l.includes('family') && !l.includes('expatriate') && !l.includes('member')); });
  if (q) out.qid_set = check(q);

  // Tag the Next button for a reliable Playwright click.
  document.querySelectorAll('[data-clark-next-btn]').forEach(e => e.removeAttribute('data-clark-next-btn'));
  const txt = (b) => ((b.innerText || b.textContent || '') + ' ' + (b.value || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  const btns = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]')).filter(vis);
  let nx = btns.find(b => txt(b) === 'next') || btns.find(b => /\bnext\b/.test(txt(b))) || btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit');
  if (nx) { nx.setAttribute('data-clark-next-btn', '1'); out.next_found = true; }
  return out;
}
"""


_READ_EDITABLE_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0'; };
  // Scan the topmost open modal if one is up, else the WHOLE document (narrowing to a single
  // container used to miss the address form â€” different portals nest it differently).
  const modalSel = '.modal.show, .modal.in, .modal[style*="display: block"], [role=dialog], .ui-dialog, [class*=modal][class*=show], [class*=modal][class*=open]';
  const modals = Array.from(document.querySelectorAll(modalSel)).filter(vis);
  const editableCount = (f) => f.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]):not([type=password]):not([type=search]):not([type=file]), select, textarea').length;
  let root = document;
  if (modals.length) {
    root = modals[modals.length - 1];
  } else {
    // Prefer the visible <form> with the most editable fields (the address form), else the document.
    const forms = Array.from(document.querySelectorAll('form')).filter(vis);
    let best = null, bestN = 1;
    forms.forEach((f) => { const n = editableCount(f); if (n > bestN) { bestN = n; best = f; } });
    root = best || document;
  }
  const labelOf = (el) => {
    let t = [el.getAttribute('aria-label'), el.getAttribute('placeholder'), el.getAttribute('title')].filter(Boolean).join(' ');
    try { if (el.id) { const l = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]'); if (l) t += ' ' + l.textContent; } } catch (e) {}
    const pl = el.closest('label'); if (pl) t += ' ' + pl.textContent;
    const cell = el.closest('td'); if (cell && !clean(t)) { const prev = cell.previousElementSibling; if (prev) t += ' ' + prev.textContent; }
    if (!clean(t)) {   // walk back a few siblings for a preceding label/caption
      let p = el.previousElementSibling, hops = 0;
      while (p && hops < 3 && !clean(t)) { if (/^(label|span|td|th|div|strong|b|p|dt)$/i.test(p.tagName)) t += ' ' + (p.textContent || ''); p = p.previousElementSibling; hops++; }
    }
    return clean(t).replace(/[:*]\s*$/, '');
  };
  const SKIP = /captcha|csrf|_token|xsrf/i;          // narrow: don't drop real address fields
  const SKIP_TYPE = ['hidden', 'submit', 'button', 'reset', 'image', 'file', 'password', 'search'];
  document.querySelectorAll('[data-clark-edit]').forEach(e => e.removeAttribute('data-clark-edit'));
  const out = []; const seen = {}; let i = 0;
  Array.from(root.querySelectorAll('input, select, textarea')).forEach((el) => {
    if (!vis(el) || el.disabled) return;             // include readonly: showing > hiding (fill via setter still works)
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (tag === 'input' && SKIP_TYPE.includes(type)) return;
    const nm = el.getAttribute('name') || el.id || '';
    if (!nm || seen[nm]) return;
    if (SKIP.test(nm)) return;
    seen[nm] = 1;
    // TAG the exact element we surface, so we can fill THIS element back by tag â€” robust against
    // name/id mismatches, duplicate names, and case differences.
    el.setAttribute('data-clark-edit', String(i));
    let value = el.value || ''; let options = null;
    if (tag === 'select') { options = Array.from(el.options).map(o => clean(o.text)).filter(Boolean);
      value = el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : ''; }
    else if (type === 'checkbox' || type === 'radio') { value = el.checked ? 'true' : 'false'; }
    out.push({key: String(i), name: nm, label: labelOf(el) || '',
              type: tag === 'select' ? 'select' : (tag === 'textarea' ? 'textarea' : type || 'text'),
              value: clean(value), options});
    i++;
  });
  return {fields: out.slice(0, 30), count: out.length,
          scope: root === document ? 'document' : (root.id || root.className || (root.tagName || '').toLowerCase() || 'scope')};
}
"""


_FILL_EDITABLE_JS = r"""
(args) => {
  const vals = args.values || {};   // keyed by the data-clark-edit index from _READ_EDITABLE_JS
  const clean = (s) => (s == null ? '' : String(s)).replace(/\s+/g, ' ').trim();
  const setNative = (el, v) => {
    try {
      const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype
                  : (el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype);
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      try { el.removeAttribute('readonly'); } catch (e) {}
      setter.call(el, v);
    } catch (e) { el.value = v; }
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const filled = []; const missed = [];   // missed = couldn't set yet (e.g. a cascading select whose options haven't loaded)
  Object.keys(vals).forEach((k) => {
    const el = document.querySelector('[data-clark-edit="' + (window.CSS && CSS.escape ? CSS.escape(k) : k) + '"]');
    if (!el) { missed.push(k); return; }
    const v = vals[k]; const tag = el.tagName.toLowerCase(); const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'select') {
      const want = clean(v);
      if (!want) { filled.push(k); return; }
      // Already on the desired option? leave it (so re-passes don't reset a cascading dropdown).
      const cur = el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : '';
      if (cur && cur === want) { filled.push(k); return; }
      // Match by cleaned option text or value (the read collapses whitespace, so compare cleaned).
      const opts = Array.from(el.options);
      let opt = opts.find(o => clean(o.text) === want || clean(o.value) === want)
             || opts.find(o => clean(o.text).toLowerCase() === want.toLowerCase());
      if (opt) { setNative(el, opt.value); filled.push(k); }
      else { missed.push(k); }   // options likely not loaded yet (Zone -> Street -> Building cascade) -> retry later
    } else if (type === 'checkbox' || type === 'radio') {
      const want = String(v).toLowerCase() === 'true' || String(v) === '1' || String(v).toLowerCase() === 'on';
      if (el.checked !== want) el.click(); filled.push(k);
    } else { setNative(el, String(v)); filled.push(k); }
  });
  return {filled: filled, missed: missed};
}
"""


# --------------------------------------------------------------------------- #
# Session registry
# --------------------------------------------------------------------------- #
_SESSIONS: dict[str, BrowserSession] = {}
_LOCK = threading.Lock()


def get_session(session_id: str, create: bool = True) -> BrowserSession | None:
    with _LOCK:
        sess = _SESSIONS.get(session_id)
        if sess is None and create:
            sess = BrowserSession(session_id)
            _SESSIONS[session_id] = sess
        return sess


def close_session(session_id: str) -> bool:
    with _LOCK:
        sess = _SESSIONS.pop(session_id, None)
    if sess:
        sess.close()
        return True
    return False
