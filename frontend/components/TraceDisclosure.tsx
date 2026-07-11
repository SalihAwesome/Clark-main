"use client";

import { useState } from "react";
import { StepTimeline } from "./StepTimeline";
import { Icon } from "./Icon";
import type { TraceStep } from "./types";

/**
 * Wraps the agent's step trace in a collapsible disclosure so the conversation stays clean:
 * while the agent is working it shows "Processing…" (expanded); once done it auto-collapses to a
 * "✓ Steps · N" summary the user can re-open. The final answer renders BELOW this, in the parent.
 *
 * Open state follows `busy` by default (open while working, closed when finished); a manual click
 * pins it open/closed thereafter.
 */
export function TraceDisclosure({ steps, busy }: { steps: TraceStep[]; busy: boolean }) {
  const [override, setOverride] = useState<boolean | null>(null);
  const open = override === null ? busy : override;
  // Count actual STEPS (tool actions), not every trace event — a single step emits a
  // thought + action + observation (+ screenshot), so steps.length over-counts ~4×.
  const stepCount = steps.filter((s) => s.type === "action").length;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="flex w-full items-center gap-2 rounded-xl border border-line bg-surface/40 px-3 py-2 text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground backdrop-blur-sm transition-all duration-200 ease-expo-out hover:border-accent/60 hover:text-accent"
      >
        <Icon name="chevron-right" size={13} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        {busy ? (
          <span className="flex items-center gap-2 text-accent">
            Processing
            <span className="flex gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
          </span>
        ) : (
          <span className="flex items-center gap-1.5"><Icon name="check" size={13} /> Steps · {stepCount}</span>
        )}
        <span className="ml-auto text-[10px] tracking-normal text-muted-foreground/60">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="mt-2">
          <StepTimeline steps={steps} />
        </div>
      )}
    </div>
  );
}
