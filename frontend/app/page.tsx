"use client";

import { useEffect, useRef, useState } from "react";
import { ClarkMark } from "@/components/ClarkMark";
import { Marquee } from "@/components/Marquee";
import { TraceDisclosure } from "@/components/TraceDisclosure";
import { LivePreview, type LiveShot } from "@/components/LivePreview";
import { ProfilePanel } from "@/components/ProfilePanel";
import { HistoryPanel } from "@/components/HistoryPanel";
import { Markdown } from "@/components/Markdown";
import { Icon } from "@/components/Icon";
import type { ChatMsg, PaymentField, Pending, ProfileField, SavedCredential } from "@/components/types";

type Mode = "chat" | "agent";

// Same-origin by default (Next rewrites /api/* to the backend). If the dev proxy buffers the SSE
// stream (steps appearing late), set NEXT_PUBLIC_BACKEND_URL=http://localhost:8008 to stream the
// trace DIRECTLY from the backend (CORS is open), so each step shows the instant it happens.
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";

type QuickAction = { label: string; text: string };

// AGENT mode — live tasks the agent performs end-to-end (drives the browser, logs in, fills forms).
const AGENT_ACTIONS: QuickAction[] = [
  { label: "Search", text: "Search for the latest news about artificial intelligence" },
  { label: "Form", text: "Log into the-internet.herokuapp.com/login with username tomsmith and password SuperSecretPassword!" },
  { label: "Research", text: "Find and summarize a research paper on climate change" },
  { label: "Rates", text: "Check the current exchange rate between USD and EUR" },
  { label: "Document", text: "Visit a Wikipedia page and save a summary as a document" },
  { label: "Registration", text: "Visit a Wikipedia page about Python and save a summary as a document" },
];

// CHAT mode — informational / how-to questions answered with knowledge (no browser actions).
const CHAT_ACTIONS: QuickAction[] = [
  { label: "Programming", text: "What are the main differences between Python and JavaScript?" },
  { label: "Web dev", text: "How do I set up a Node.js project with Express?" },
  { label: "Explain", text: "Explain how REST APIs work in simple terms" },
  { label: "Learning", text: "What's the best way to learn TypeScript?" },
  { label: "DevOps", text: "How do I deploy a Next.js app to Vercel?" },
  { label: "Concepts", text: "Explain the concept of serverless computing" },
];

const MARQUEE = [
  "BROWSER CONTROL", "FORM FILLING", "WEB SEARCH", "HUMAN-IN-THE-LOOP",
  "LIVE SCREENSHOTS", "MULTI-STEP TASKS", "DOCUMENT GENERATION",
];

export default function Home() {
  const [mode, setMode] = useState<Mode>("agent");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [shot, setShot] = useState<LiveShot | null>(null);
  const [files, setFiles] = useState<{ name: string; bytes: number }[]>([]);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileFields, setProfileFields] = useState<ProfileField[]>([]);
  const [profileValues, setProfileValues] = useState<Record<string, string>>({});
  const [paymentFields, setPaymentFields] = useState<PaymentField[]>([]);
  const [paymentValues, setPaymentValues] = useState<Record<string, string>>({});
  const [credentials, setCredentials] = useState<SavedCredential[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [modeSwitch, setModeSwitch] = useState<Mode | null>(null);
  const sessionId = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // In agent mode a conversation is ONE task: once a prompt is sent, the input
  // locks and the user must start a new conversation. Chat mode stays multi-turn.
  const agentLocked = mode === "agent" && messages.some((m) => m.role === "user");

  useEffect(() => {
    sessionId.current = (globalThis.crypto?.randomUUID?.() as string) || `sess-${Date.now()}`;
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // Load the saved-information profile + payment card (field defs + current values) once.
  useEffect(() => {
    (async () => {
      try {
        const j = await (await fetch("/api/profile")).json();
        setProfileFields(j.fields || []);
        setProfileValues(j.values || {});
      } catch { /* ignore */ }
      try {
        const p = await (await fetch("/api/payment")).json();
        setPaymentFields(p.fields || []);
        setPaymentValues(p.values || {});
      } catch { /* ignore */ }
      refreshCredentials();
    })();
  }, []);

  async function savePayment(values: Record<string, string>) {
    try {
      const r = await fetch("/api/payment", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      const j = await r.json();
      setPaymentValues(j.values || {});
    } catch { /* ignore */ }
  }

  async function refreshCredentials() {
    try {
      const j = await (await fetch("/api/credentials")).json();
      setCredentials(j.credentials || []);
    } catch { /* ignore */ }
  }

  async function saveCredential(cred: Partial<SavedCredential>) {
    try {
      const r = await fetch("/api/credentials", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cred),
      });
      const j = await r.json();
      setCredentials(j.credentials || []);
    } catch { /* ignore */ }
  }

  async function deleteCredential(host: string) {
    try {
      const r = await fetch(`/api/credentials/${encodeURIComponent(host)}`, { method: "DELETE" });
      const j = await r.json();
      setCredentials(j.credentials || []);
    } catch { /* ignore */ }
  }

  async function refreshProfile() {
    try {
      const j = await (await fetch("/api/profile")).json();
      setProfileValues(j.values || {});
    } catch { /* ignore */ }
  }

  async function saveProfile(values: Record<string, string>) {
    try {
      const r = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      const j = await r.json();
      setProfileValues(j.values || {});
    } catch { /* ignore */ }
  }

  async function refreshFiles() {
    try {
      const j = await (await fetch("/api/workspace")).json();
      setFiles((j.files || []).filter((f: any) => !f.name.endsWith(".png")));
    } catch { /* ignore */ }
  }

  function updateLast(fn: (m: ChatMsg) => ChatMsg) {
    setMessages((msgs) => {
      const copy = [...msgs];
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });
  }

  function applyEvent(evt: any) {
    switch (evt.type) {
      case "delta": updateLast((m) => ({ ...m, content: m.content + evt.content })); break;
      case "thought": updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "thought", content: evt.content }] })); break;
      case "action": updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "action", tool: evt.tool, input: evt.input }] })); break;
      case "observation": updateLast((m) => {
        const updated: any = { ...m, trace: [...(m.trace ?? []), { type: "observation", tool: evt.tool, result: evt.result }] };
        if (evt.tool === "save_document" && evt.result?.saved_to) {
          const parts = (evt.result.saved_to as string).split(/[/\\]/);
          updated.files = [...(m.files ?? []), { name: parts[parts.length - 1], bytes: (evt.result.bytes as number) || 0 }];
        }
        return updated;
      }); break;
      case "screenshot":
        setShot({ url: evt.url, page_url: evt.page_url, title: evt.title });
        updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "screenshot", url: evt.url, page_url: evt.page_url, title: evt.title }] }));
        break;
      case "awaiting_user":
        setPending({ reason: evt.reason, kind: evt.kind, fields: evt.fields, image: evt.image, details: evt.details });
        updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "awaiting_user", reason: evt.reason, kind: evt.kind }] }));
        break;
      case "final": updateLast((m) => ({ ...m, content: evt.content })); break;
      case "stopped": updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "stopped", content: evt.content || "Stopped." }] })); break;
      case "error": updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "error", content: evt.content }] })); break;
    }
  }

  async function stream(url: string, body: object) {
    setBusy(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch(API_BASE + url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal });
      if (!res.body) throw new Error("No response stream");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (line.startsWith("data:")) applyEvent(JSON.parse(line.slice(5).trim()));
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        updateLast((m) => ({ ...m, content: m.content + `\n\n⚠ ${err.message ?? err}` }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      refreshFiles();
    }
  }

  async function stopAgent() {
    try { abortRef.current?.abort(); } catch { /* ignore */ }
    try {
      await fetch("/api/agent/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId.current }),
      });
    } catch { /* ignore */ }
    setBusy(false);
    setPending(null);
    updateLast((m) => ({ ...m, trace: [...(m.trace ?? []), { type: "stopped", content: "Stopped by user." }] }));
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    if (mode === "agent" && messages.some((m) => m.role === "user")) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setPending(null);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "", trace: mode === "agent" ? [] : undefined }]);
    setInput("");
    await stream(`/api/${mode}`, { message: text, history, session_id: sessionId.current, lang: "en" });
  }

  async function resume(note: string, approve: boolean) {
    if (busy) return;
    setPending(null);
    await stream("/api/agent/resume", { session_id: sessionId.current, note: approve ? note : `no — ${note}` });
  }

  async function submitCredentials(creds: Record<string, string>, remember: boolean) {
    if (busy) return;
    setPending(null);
    await stream("/api/agent/credentials", { session_id: sessionId.current, credentials: creds, remember });
    if (remember) refreshCredentials();
  }

  async function submitInputs(values: Record<string, string>, saveKeys: string[]) {
    if (busy) return;
    setPending(null);
    await stream("/api/agent/inputs", { session_id: sessionId.current, values, save_keys: saveKeys });
    if (saveKeys.length) refreshProfile();
  }

  async function submitCaptcha(code: string) {
    if (busy) return;
    setPending(null);
    await stream("/api/agent/captcha", { session_id: sessionId.current, code });
  }

  async function submitOtp(code: string) {
    if (busy) return;
    setPending(null);
    await stream("/api/agent/otp", { session_id: sessionId.current, code });
  }

  function clearUI() {
    setMessages([]);
    setPending(null);
    setShot(null);
    setFiles([]);
    setInput("");
  }

  function closeSession(id: string) {
    fetch("/api/session/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: id }),
    }).catch(() => {});
  }

  function newConversation() {
    if (busy) return;
    closeSession(sessionId.current);
    sessionId.current = (globalThis.crypto?.randomUUID?.() as string) || `sess-${Date.now()}`;
    clearUI();
  }

  function switchMode(target: Mode) {
    if (target === mode) return;
    const inProgress = busy || messages.length > 0;
    if (inProgress) {
      setModeSwitch(target);
      return;
    }
    doSwitchMode(target);
  }

  function doSwitchMode(target: Mode) {
    try { abortRef.current?.abort(); } catch { /* ignore */ }
    if (busy) {
      fetch("/api/agent/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId.current }),
      }).catch(() => {});
    }
    closeSession(sessionId.current);
    sessionId.current = (globalThis.crypto?.randomUUID?.() as string) || `sess-${Date.now()}`;
    clearUI();
    setBusy(false);
    setMode(target);
    setModeSwitch(null);
  }

  function deleteConversation() {
    if (busy) return;
    closeSession(sessionId.current);
    clearUI();
  }

  const fresh = messages.length === 0;

  const navBtn =
    "flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-xs font-semibold uppercase tracking-tight text-muted-foreground transition-all duration-200 ease-expo-out hover:border-accent/60 hover:text-accent disabled:opacity-40";

  return (
    <div className="mx-auto flex h-screen max-w-[1400px] flex-col">
      {/* NAV */}
      <header className="drag-region flex items-center gap-4 border-b border-line px-5 py-3 backdrop-blur-md">
        <ClarkMark />
        <span className="ml-1 flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          <Icon name="globe" size={12} />
          Web
        </span>
        <div className="no-drag ml-auto flex items-center gap-2">
          <button
            onClick={() => setHistoryOpen(true)}
            title="History"
            className={navBtn}
          >
            <Icon name="clock" size={14} /> History
          </button>
          <button
            onClick={() => setProfileOpen(true)}
            title="My Information"
            className={navBtn}
          >
            <Icon name="id-card" size={14} /> My Info
          </button>
          <button
            onClick={newConversation}
            disabled={busy}
            title="Start a new conversation"
            className={navBtn}
          >
            <Icon name="plus" size={14} /> New
          </button>
          <button
            onClick={deleteConversation}
            disabled={busy || fresh}
            title="Delete this conversation"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-line text-muted-foreground transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon disabled:opacity-40"
          >
            <Icon name="trash" size={15} />
          </button>
          <div className="flex rounded-lg border border-white/[0.06] bg-white/[0.02] p-1 backdrop-blur-sm">
            {(["chat", "agent"] as Mode[]).map((m) => (
              <button key={m} onClick={() => switchMode(m)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition-all duration-300 ${mode === m ? "bg-accent text-white shadow-accent-glow animate-glow-pulse" : "text-muted-foreground hover:scale-105 hover:bg-white/[0.05] hover:text-foreground"}`}>
                {m === "chat" ? "Chat" : "Agent"}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* MARQUEE */}
      <Marquee items={MARQUEE} />

      {/* BODY */}
      <div className={`grid min-h-0 flex-1 ${mode === "agent" && !fresh ? "lg:grid-cols-[1fr_400px]" : "grid-cols-1"}`}>
        <div className="flex min-h-0 flex-col">
          <div ref={scrollRef} className="no-scrollbar flex-1 overflow-y-auto px-5 py-5">
            {fresh ? (
              <Hero mode={mode} onPick={send} />
            ) : (
              <div className="mx-auto max-w-3xl space-y-5">
                {messages.map((m, i) => (
                  <div key={i} className={`animate-fade-up ${m.role === "user" ? "flex justify-end" : ""}`}>
                    {m.role === "user" ? (
                      <div className="max-w-[85%] rounded-2xl border border-accent/30 bg-accent/[0.08] px-4 py-2.5 text-sm text-foreground backdrop-blur-sm">
                        {m.content}
                      </div>
                    ) : (
                      <div className="border-l border-accent/40 pl-4">
                        <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.3em] text-accent">Clark</div>
                        {m.trace && m.trace.length > 0 && (
                          <TraceDisclosure steps={m.trace} busy={busy && i === messages.length - 1} />
                        )}
                        {m.files && m.files.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {m.files.map((f) => (
                              <a
                                key={f.name}
                                href={`/api/workspace/download/${encodeURIComponent(f.name)}`}
                                download={f.name}
                                className="group flex items-center gap-2.5 rounded-xl border border-accent/25 bg-accent/[0.05] px-3.5 py-2.5 text-xs text-foreground transition-all duration-200 ease-expo-out hover:border-accent/50 hover:bg-accent/[0.12] hover:shadow-[0_2px_8px_-2px_rgba(176,141,87,0.2)]"
                              >
                                <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-accent/20 bg-accent/[0.08] text-accent transition-all duration-200 group-hover:bg-accent/[0.14]">
                                  <Icon name="download" size={13} />
                                </span>
                                <span className="flex flex-col">
                                  <span className="font-medium leading-tight">{f.name}</span>
                                  <span className="text-[10px] text-muted-foreground/60">
                                    {(f.bytes / 1024).toFixed(1)} KB
                                  </span>
                                </span>
                              </a>
                            ))}
                          </div>
                        )}
                        {m.content ? (
                          <div className={(m.trace?.length || (m.files?.length ?? 0) > 0) ? "mt-2" : ""}>
                            <Markdown content={m.content} />
                          </div>
                        ) : busy ? (
                          <div className="flex gap-1 py-2">
                            <span className="typing-dot h-2 w-2 rounded-full bg-accent" /><span className="typing-dot h-2 w-2 rounded-full bg-accent" /><span className="typing-dot h-2 w-2 rounded-full bg-accent" />
                          </div>
                        ) : null}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* COMMAND BAR */}
          <div className="border-t border-line px-5 py-4 backdrop-blur-md">
            {agentLocked ? (
              <div className="mx-auto flex max-w-3xl items-center gap-3 rounded-2xl border border-line bg-surface/40 px-4 py-3 backdrop-blur-sm">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Agent runs one task per conversation. Start a new one to run another.
                </span>
                <button
                  onClick={newConversation}
                  disabled={busy}
                  className="ms-auto h-9 shrink-0 rounded-xl bg-accent px-4 text-xs font-bold uppercase tracking-tight text-accent-foreground transition-all duration-200 ease-expo-out hover:opacity-90 hover:scale-[1.02] active:scale-95 disabled:opacity-40"
                >
                  <span className="flex items-center justify-center gap-1.5"><Icon name="plus" size={14} /> New Conversation</span>
                </button>
                {busy && (
                  <button
                    onClick={stopAgent}
                    className="group relative inline-flex h-9 shrink-0 items-center gap-2 overflow-hidden rounded-xl border border-maroon/25 px-4 text-xs font-medium text-[#D89A8A] transition-all duration-300 ease-expo-out [background:linear-gradient(180deg,rgba(183,112,127,0.16)_0%,rgba(183,112,127,0.09)_100%)] shadow-[0_1px_0_0_rgba(255,255,255,0.06)_inset] btn-sheen [--btn-sheen-tint:rgba(232,176,140,0.3)] [--btn-sheen-speed:5.5s] hover:border-maroon/45 hover:text-[#E9B58C] hover:[background:linear-gradient(180deg,rgba(183,112,127,0.24)_0%,rgba(183,112,127,0.14)_100%)] hover:[--btn-sheen-speed:2.6s] active:scale-[0.98]"
                  >
                    <span className="btn-stop-dot" aria-hidden="true" />
                    <span className="relative z-[2]">Stop</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="mx-auto flex max-w-3xl items-center gap-2">
                <div className="group relative flex-1">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); send(input); } }}
                    placeholder={mode === "agent" ? "Command the agent…" : "Message Clark…"}
                    className="h-14 w-full rounded-xl border border-white/[0.08] bg-gradient-to-b from-white/[0.08] to-white/[0.04] px-5 text-base font-medium text-foreground placeholder:text-foreground-subtle backdrop-blur-xl transition-all duration-300 focus:border-accent focus:bg-white/[0.1] focus:shadow-[0_0_0_3px_rgba(176,141,87,0.3),0_4px_20px_rgba(176,141,87,0.2)] focus:outline-none"
                  />
                  <div className="pointer-events-none absolute inset-x-0 -bottom-px h-px bg-gradient-to-r from-transparent via-accent to-transparent opacity-0 transition-opacity duration-500 group-focus-within:opacity-100" />
                </div>
                {busy ? (
                  <button onClick={stopAgent}
                    className="group relative inline-flex h-14 shrink-0 items-center gap-2.5 overflow-hidden rounded-xl border border-maroon/25 px-6 text-base font-medium text-[#D89A8A] transition-all duration-300 ease-expo-out [background:linear-gradient(180deg,rgba(183,112,127,0.16)_0%,rgba(183,112,127,0.09)_100%)] shadow-[0_1px_0_0_rgba(255,255,255,0.06)_inset] btn-sheen [--btn-sheen-tint:rgba(232,176,140,0.3)] [--btn-sheen-speed:5.5s] hover:border-maroon/45 hover:text-[#E9B58C] hover:[background:linear-gradient(180deg,rgba(183,112,127,0.24)_0%,rgba(183,112,127,0.14)_100%)] hover:[--btn-sheen-speed:2.6s] active:scale-[0.98]">
                    <span className="btn-stop-dot" aria-hidden="true" />
                    <span className="relative z-[2]">Stop</span>
                  </button>
                ) : (
                  <button onClick={() => send(input)} disabled={!input.trim()}
                    className="group relative h-14 shrink-0 overflow-hidden rounded-xl px-6 text-base font-medium text-accent-foreground transition-all duration-300 ease-expo-out [background:linear-gradient(180deg,#C6A268_0%,#B08D57_55%,#9E7C4A_100%)] shadow-[0_1px_0_0_rgba(255,255,255,0.22)_inset,0_-1px_0_0_rgba(0,0,0,0.18)_inset,0_2px_10px_-2px_rgba(176,141,87,0.45)] btn-sheen [--btn-sheen-tint:rgba(255,247,235,0.5)] enabled:btn-send-breathe hover:brightness-[1.06] hover:[--btn-sheen-speed:1.8s] active:scale-[0.98] active:brightness-100 disabled:cursor-not-allowed disabled:[background:#2E3A4F] disabled:text-foreground-subtle disabled:shadow-none disabled:brightness-100">
                    <span className="relative z-[2]">Send<span className="btn-send-arrow" aria-hidden="true">→</span></span>
                  </button>
                )}
              </div>
            )}
            <p className="mx-auto mt-2 max-w-3xl text-[10px] uppercase tracking-wider text-muted-foreground/60">
              {mode === "agent"
                ? "Agent drives a real browser & pauses for you to log in, enter OTPs, and approve actions"
                : "Direct chat with Clark"}
            </p>
          </div>
        </div>

        {/* LIVE PREVIEW */}
        {mode === "agent" && !fresh && (
          <div className="min-h-0 overflow-y-auto border-l border-line p-4">
            <LivePreview shot={shot} pending={pending} busy={busy} files={files} sessionId={sessionId.current} apiBase={API_BASE} onResume={resume} onCredentials={submitCredentials} onSubmitInputs={submitInputs} onSubmitCaptcha={submitCaptcha} onSubmitOtp={submitOtp} onCancel={() => resume("cancelled", false)} />
          </div>
        )}
      </div>

      <ProfilePanel
        open={profileOpen}
        fields={profileFields}
        values={profileValues}
        paymentFields={paymentFields}
        paymentValues={paymentValues}
        credentials={credentials}
        onClose={() => setProfileOpen(false)}
        onSave={saveProfile}
        onSavePayment={savePayment}
        onSaveCredential={saveCredential}
        onDeleteCredential={deleteCredential}
      />

      <HistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} />

      {/* Styled mode-switch confirmation */}
      {modeSwitch && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
             onClick={() => setModeSwitch(null)}>
          <div className="glow animate-scale-in w-full max-w-md rounded-2xl border border-accent/40 bg-surface/90 p-6 backdrop-blur-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 text-xs font-bold uppercase tracking-[0.25em] text-accent">
              Switch to {modeSwitch} mode?
            </div>
            <p className="text-sm leading-relaxed text-foreground">
              {busy
                ? "The agent is still working on this task. Switching stops it and starts a new conversation."
                : "This starts a new conversation — the current one will be cleared."}
            </p>
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => doSwitchMode(modeSwitch)}
                className="flex-1 rounded-xl bg-accent px-4 py-3 text-sm font-bold uppercase tracking-tight text-accent-foreground transition-all duration-200 ease-expo-out hover:opacity-90 hover:scale-[1.02] active:scale-95"
              >
                Switch & Start New
              </button>
              <button
                onClick={() => setModeSwitch(null)}
                className="rounded-xl border border-line px-4 py-3 text-sm font-bold uppercase tracking-tight text-foreground transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Hero({ mode, onPick }: { mode: Mode; onPick: (t: string) => void }) {
  const onMove = (e: React.MouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--mouse-x", `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty("--mouse-y", `${e.clientY - r.top}px`);
  };

  return (
    <div className="mx-auto max-w-5xl py-10 pt-4">
      <h1 className="text-center font-display text-[clamp(2.5rem,9vw,7rem)] font-extrabold leading-[0.9] tracking-tightest text-foreground">
        Autonomous<br />
        <span className="text-accent">Web Agent</span>
      </h1>
      <p className="mx-auto mt-6 max-w-2xl text-center text-sm leading-relaxed text-muted-foreground">
        One agent that acts — it drives a real browser, searches the web, fills forms,
        logs in, extracts data, and saves documents. Powered by Gemini AI.
      </p>

      <div className="mt-10 space-y-4">
        <div className="flex items-center gap-4">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          <span className="animate-pulse-glow font-mono text-xs uppercase tracking-widest text-foreground-subtle">
            {mode === "agent" ? "Try an agent task" : "Try a question"}
          </span>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {(mode === "agent" ? AGENT_ACTIONS : CHAT_ACTIONS).map((q, i) => (
            <button
              key={i}
              onClick={() => onPick(q.text)}
              onMouseMove={onMove}
              style={{ animationDelay: `${(i * 0.08).toFixed(2)}s` }}
              className="card-spotlight group animate-fade-up cursor-pointer rounded-2xl border border-line bg-surface/40 p-5 text-start backdrop-blur-xl transition-all duration-300 ease-expo-out hover:-translate-y-1 hover:border-line-hover hover:shadow-card-hover"
            >
              <div className="relative z-10 flex items-start gap-4">
                <span className="font-display text-3xl font-bold leading-none text-foreground-subtle transition-all duration-200 group-hover:scale-110 group-hover:text-gradient-accent">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="font-mono text-[10px] uppercase tracking-widest text-accent group-hover:animate-shimmer">
                    {q.label}
                  </div>
                  <p className="text-sm leading-relaxed text-foreground transition-colors duration-200 group-hover:text-white">
                    {q.text}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
