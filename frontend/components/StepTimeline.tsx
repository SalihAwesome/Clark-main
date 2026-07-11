// The live agent reasoning, rendered as a kinetic timeline with massive step
// numbers as decorative graphic shapes (a signature of the design system).
import type { TraceStep } from "./types";
import { Icon } from "./Icon";

const TOOL_LABELS: Record<string, string> = {
  web_search: "SEARCH WEB",
  open_page: "OPEN PAGE",
  read_page: "READ PAGE",
  see_page: "MARK ELEMENTS",
  click_mark: "CLICK BOX",
  fill_mark: "FILL BOX",
  fill_date: "FILL DATE",
  request_credentials: "ASK FOR LOGIN",
  fill_login: "AUTO LOGIN",
  list_form_fields: "INSPECT FORM",
  fill_field: "FILL FIELD",
  click: "CLICK",
  pause_for_user: "HAND TO USER",
  see_screen_marks: "MARK SCREEN",
  click_mark_screen: "CLICK BOX",
  generate_official_letter: "WRITE LETTER",
  save_document: "SAVE FILE",
  see_screen: "SEE SCREEN",
  mouse_click: "CLICK SCREEN",
  type_text: "TYPE",
  press_keys: "HOTKEY",
  scroll: "SCROLL",
  open_application: "OPEN APP",
};

function actionSummary(tool: string, input: Record<string, unknown>): string {
  if (!input) return "";
  if (tool === "click_mark" || tool === "click_mark_screen") return `box #${input.n}`;
  if (tool === "fill_mark") return `box #${input.n} ← "${String(input.text ?? "").slice(0, 40)}"`;
  if (tool === "fill_login") return "filling credentials securely";
  const v =
    (input.query as string) ||
    (input.url as string) ||
    (input.question as string) ||
    (input.name as string) ||
    (input.topic as string) ||
    (input.concept as string) ||
    (input.target as string) ||
    (input.text as string) ||
    Object.values(input).map(String).join(", ");
  return v?.length > 90 ? v.slice(0, 90) + "…" : v || "";
}

export function StepTimeline({ steps }: { steps: TraceStep[] }) {
  if (steps.length === 0) return null;
  // number only the tool actions
  let n = 0;
  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.3em] text-accent/80">
        ── Agent Trace
      </div>
      <ul className="space-y-2.5">
        {steps.map((s, i) => {
          if (s.type === "action") n += 1;
          return (
            <li key={i} className="animate-slide-in">
              {s.type === "thought" && (
                <p className="pl-[3.2rem] text-sm italic text-muted-foreground">{s.content}</p>
              )}

              {s.type === "action" && (
                <div className="flex items-center gap-3">
                  <span className="w-12 shrink-0 text-right font-display text-3xl font-bold leading-none text-muted-foreground/30">
                    {String(n).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1 border-l-2 border-accent pl-3">
                    <div className="text-sm font-bold uppercase tracking-tight text-accent">
                      {TOOL_LABELS[s.tool] ?? s.tool}
                    </div>
                    {actionSummary(s.tool, s.input) && (
                      <div className="truncate text-[12px] text-muted-foreground">
                        {actionSummary(s.tool, s.input)}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {s.type === "observation" && (
                <div className="pl-[3.2rem]">{renderObs(s.result)}</div>
              )}

              {s.type === "screenshot" && (
                <a
                  href={`/api/screenshot/${s.url}`}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-[3.2rem] block max-w-md overflow-hidden rounded-xl border border-line transition-all duration-200 ease-expo-out hover:border-accent/60"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/api/screenshot/${s.url}`} alt={s.title || "frame"} className="max-h-44 w-full object-cover object-top" />
                </a>
              )}

              {s.type === "awaiting_user" && (
                <div className="ml-[3.2rem] rounded-r-lg border-l-2 border-maroon bg-maroon/10 px-3 py-1.5 text-sm font-medium text-sand">
                  {s.reason}
                </div>
              )}

              {s.type === "stopped" && (
                <div className="ml-[3.2rem] rounded-r-lg border-l-2 border-maroon bg-maroon/10 px-3 py-1.5 text-sm font-bold uppercase tracking-wide text-maroon">
                  ■ {s.content}
                </div>
              )}

              {s.type === "error" && (
                <div className="ml-[3.2rem] rounded-r-lg border-l-2 border-maroon bg-maroon/10 px-3 py-1.5 text-sm text-maroon">
                  {s.content}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function renderObs(result: Record<string, unknown>) {
  if (result?.error) return <p className="flex items-start gap-1.5 text-[12px] text-maroon"><Icon name="alert" size={13} className="mt-0.5 shrink-0" /> {String(result.error)}</p>;
  if (Array.isArray((result as any).results)) {
    const rs = (result as any).results as Array<{ title: string; url: string }>;
    return (
      <div className="space-y-0.5">
        {rs.slice(0, 3).map((r, i) => (
          <a key={i} href={r.url} target="_blank" rel="noreferrer" className="block truncate text-[12px] text-accent hover:underline">
            → {r.title || r.url}
          </a>
        ))}
      </div>
    );
  }
  if (result?.understanding)
    return <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-muted-foreground"><Icon name="eye" size={13} className="mt-0.5 shrink-0" /> {String(result.understanding).slice(0, 200)}…</p>;
  if (result?.saved_to)
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] uppercase tracking-wide text-accent">
        <Icon name="check" size={11} /> saved · {String(result.saved_to)}
      </span>
    );
  if (result?.information || result?.summary || result?.guidance || result?.explanation)
    return (
      <p className="text-[12px] leading-relaxed text-muted-foreground">
        {String(result.information || result.summary || result.guidance || result.explanation).slice(0, 200)}…
      </p>
    );
  if (result?.title || result?.url)
    return <p className="text-[12px] text-muted-foreground"><span className="text-foreground">{String(result.title || "Page")}</span></p>;
  return null;
}
