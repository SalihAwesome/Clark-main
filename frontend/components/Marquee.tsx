// Infinite CSS marquee — a quiet ticker of capabilities.
// Content is duplicated so the -50% translate loops seamlessly.
export function Marquee({
  items,
  fast = false,
  invert = false,
}: {
  items: string[];
  fast?: boolean;
  invert?: boolean;
}) {
  const row = [...items, ...items];
  return (
    <div
      className={`overflow-hidden border-y border-line backdrop-blur-sm ${
        invert ? "bg-accent text-accent-foreground" : "bg-surface/30 text-muted-foreground"
      }`}
    >
      <div className={`marquee-track ${fast ? "animate-marquee-fast" : "animate-marquee"}`}>
        {row.map((item, i) => (
          <span
            key={i}
            className="flex items-center gap-5 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-[0.25em]"
          >
            {item}
            <span className={invert ? "text-accent-foreground/60" : "text-accent"}>✦</span>
          </span>
        ))}
      </div>
    </div>
  );
}
