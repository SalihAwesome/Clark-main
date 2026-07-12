"use client";

import { useEffect, useState } from "react";
import { StepTimeline } from "./StepTimeline";
import { Markdown } from "./Markdown";
import { Icon } from "./Icon";
import type { AuditRecord, ConversationSummary, TraceStep } from "./types";

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-accent dark:bg-dark-accent text-accent-foreground dark:text-dark-accent-foreground",
  stopped: "bg-maroon text-foreground",
  paused: "bg-sand text-bg",
  in_progress: "bg-muted text-muted-foreground",
};

const TRACE_TYPES = ["thought", "action", "observation", "screenshot", "awaiting_user", "error", "stopped"];

export function HistoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [list, setList] = useState<ConversationSummary[]>([]);
  const [selected, setSelected] = useState<AuditRecord | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) { setSelected(null); load(); }
  }, [open]);

  async function load() {
    setLoading(true);
    try {
      const j = await (await fetch("/api/history")).json();
      setList(j.conversations || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }

  async function openConv(id: string) {
    try {
      const j = await (await fetch(`/api/history/${encodeURIComponent(id)}`)).json();
      setSelected(j);
    } catch { /* ignore */ }
  }

  async function del(id: string, e: { stopPropagation: () => void }) {
    e.stopPropagation();
    try { await fetch(`/api/history/${encodeURIComponent(id)}`, { method: "DELETE" }); } catch { /* ignore */ }
    if (selected?.id === id) setSelected(null);
    load();
  }

  if (!open) return null;

  const trace: TraceStep[] = selected
    ? (selected.transcript.filter((e) => TRACE_TYPES.includes(e.type)) as unknown as TraceStep[])
    : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-md" onClick={onClose} />
      <aside className="animate-slide-in relative flex h-full w-full max-w-2xl flex-col border-s border-line dark:border-dark-line bg-surface/95 dark:bg-dark-surface/95 backdrop-blur-xl">
        <div className="flex items-center gap-3 border-b border-line dark:border-dark-line px-5 py-4">
          {selected ? (
            <button
              onClick={() => setSelected(null)}
              className="flex h-8 items-center gap-1.5 rounded-lg border border-line dark:border-dark-line px-3 text-[11px] font-bold uppercase tracking-tight text-muted-foreground dark:text-dark-muted transition-all duration-200 ease-expo-out hover:border-accent/60 dark:hover:border-dark-accent/60 hover:text-accent dark:hover:text-dark-accent"
            >
              <Icon name="arrow-left" size={13} /> Back
            </button>
          ) : (
            <span className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.2em] text-accent dark:text-dark-accent"><Icon name="clock" size={16} /> History</span>
          )}
          <button
            onClick={onClose}
            className="ms-auto flex h-8 w-8 items-center justify-center rounded-lg border border-line dark:border-dark-line text-muted-foreground dark:text-dark-muted transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon"
            title="Close"
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!selected ? (
            loading ? (
              <p className="text-xs uppercase tracking-wide text-muted-foreground dark:text-dark-muted">Loading…</p>
            ) : list.length === 0 ? (
              <p className="text-xs uppercase tracking-wide text-muted-foreground dark:text-dark-muted">No conversations yet.</p>
            ) : (
              <ul className="space-y-2">
                {list.map((c) => (
                  <li
                    key={c.id}
                    onClick={() => openConv(c.id)}
                    className="group flex cursor-pointer items-start gap-3 rounded-xl border border-line dark:border-dark-line bg-bg/40 dark:bg-black/40 p-3 transition-all duration-200 ease-expo-out hover:border-accent/60 dark:hover:border-dark-accent/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-foreground">
                        {c.title || "Conversation"}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground dark:text-dark-muted">
                        <span className={`rounded-full px-1.5 py-0.5 font-bold ${STATUS_STYLE[c.status] || "bg-muted text-muted-foreground"}`}>{c.status}</span>
                        <span className="flex items-center gap-1 rounded-full bg-line dark:bg-dark-line px-1.5 py-0.5 font-bold text-foreground dark:text-white"><Icon name={c.mode === "chat" ? "message" : "bot"} size={11} /> {c.mode === "chat" ? "Chat" : "Agent"}</span>
                        {c.mode !== "chat" && <span>{c.num_actions ?? 0} actions</span>}
                        <span className="text-muted-foreground/50 dark:text-dark-muted/50">{(c.updated_at || "").replace("T", " ")}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => del(c.id, e)}
                      title="Delete"
                      className="flex shrink-0 items-center justify-center rounded-lg border border-line dark:border-dark-line px-2 py-1 text-muted-foreground dark:text-dark-muted opacity-0 transition-all duration-200 ease-expo-out group-hover:opacity-100 hover:border-maroon hover:text-maroon"
                    >
                      <Icon name="trash" size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )
          ) : (
            <div>
              <div className="mb-1 text-lg font-bold text-foreground">
                {selected.title}
              </div>
              <div className="mb-4 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground dark:text-dark-muted">
                <span className={`rounded-full px-1.5 py-0.5 font-bold ${STATUS_STYLE[selected.status] || "bg-muted text-muted-foreground"}`}>{selected.status}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-line dark:bg-dark-line px-1.5 py-0.5 font-bold text-foreground dark:text-white"><Icon name={selected.mode === "chat" ? "message" : "bot"} size={11} /> {selected.mode === "chat" ? "Chat" : "Agent"}</span>
                <span>{(selected.updated_at || "").replace("T", " ")}</span>
                {selected.track && <span>· {selected.track}</span>}
              </div>

              {selected.mode === "chat" ? (
                <div className="space-y-4">
                  {selected.transcript.map((e, i) =>
                    e.type === "prompt" ? (
                      <div key={i} className="flex justify-end">
                        <div className="max-w-[85%] rounded-2xl border border-accent/30 dark:border-dark-accent/30 bg-accent/[0.08] dark:bg-dark-accent/[0.08] px-3 py-2 text-sm text-foreground">
                          {String(e.content || "")}
                        </div>
                      </div>
                    ) : e.type === "answer" ? (
                      <div key={i} className="border-s border-accent/40 dark:border-dark-accent/40 ps-3">
                        <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.3em] text-accent dark:text-dark-accent">Clark</div>
                        <Markdown content={String(e.content || "")} />
                      </div>
                    ) : null
                  )}
                </div>
              ) : (
                <>
                  {(selected.prompts || []).map((p, i) => (
                    <div key={i} className="mb-3 rounded-2xl border border-accent/30 dark:border-dark-accent/30 bg-accent/[0.08] dark:bg-dark-accent/[0.08] px-3 py-2 text-sm text-foreground">
                      {p}
                    </div>
                  ))}

                  {trace.length > 0 && <StepTimeline steps={trace} />}

                  {selected.final && (
                    <div className="mt-4 border-t border-line dark:border-dark-line pt-3">
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.3em] text-accent dark:text-dark-accent">Final Answer</div>
                      <Markdown content={selected.final} />
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
