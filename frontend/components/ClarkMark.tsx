// Clark wordmark — Baked Clay "C" icon + brand name.
export function ClarkMark({ size = 34 }: { size?: number }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="relative flex items-center justify-center rounded-xl border border-line shadow-card"
        style={{ width: size, height: size, background: "linear-gradient(155deg,#C96A4D,#B05439)" }}
      >
        <svg viewBox="0 0 24 24" width={size * 0.6} height={size * 0.6} fill="none">
          <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="1.7" />
          <path d="M9 12h6" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M9 9h4M9 15h4" stroke="white" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </div>
      <div className="leading-[0.9]">
        <div className="text-xl font-bold uppercase tracking-tightest text-foreground">
          Cl<span className="text-primary">ark</span>
        </div>
        <div className="text-[9px] font-medium uppercase tracking-[0.34em] text-muted-foreground">
          Web Agent
        </div>
      </div>
    </div>
  );
}
