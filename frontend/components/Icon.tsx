import type { SVGProps } from "react";

// Inline SVG icon set (Lucide/Feather-style, dependency-free) used in place of emojis across the
// platform so the UI looks consistent and professional. All icons inherit `currentColor`.
export type IconName =
  | "chevron-right" | "check" | "maximize" | "x" | "dot" | "key" | "lock" | "hash"
  | "receipt" | "shield-check" | "clipboard" | "pencil" | "monitor" | "globe"
  | "id-card" | "credit-card" | "upload" | "plus" | "clock" | "message" | "bot"
  | "trash" | "arrow-left" | "user" | "eye" | "mic" | "alert";

const PATHS: Record<IconName, JSX.Element> = {
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  check: <path d="M20 6 9 17l-5-5" />,
  maximize: <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  dot: <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />,
  key: <><circle cx="7.5" cy="15.5" r="3.5" /><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3" /></>,
  lock: <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>,
  hash: <path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18" />,
  receipt: <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1V2l-2 1-2-1-2 1-2-1-2 1-2-1Zm4 6h8M8 12h8M8 16h5" />,
  "shield-check": <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></>,
  clipboard: <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /></>,
  pencil: <path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />,
  monitor: <><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></>,
  globe: <><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z" /></>,
  "id-card": <><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M7 15a3 3 0 0 1 6 0M10 9.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0ZM16 10h3M16 14h3" /></>,
  "credit-card": <><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /></>,
  upload: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v12" />,
  plus: <path d="M12 5v14M5 12h14" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  message: <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" />,
  bot: <><rect x="4" y="8" width="16" height="12" rx="2" /><path d="M12 4v4M9 14h.01M15 14h.01M2 14h2M20 14h2" /></>,
  trash: <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14M10 11v6M14 11v6" />,
  "arrow-left": <path d="M19 12H5M12 19l-7-7 7-7" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>,
  mic: <><rect x="9" y="2" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8" /></>,
  alert: <><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.3 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.3a2 2 0 0 0-3.4 0Z" /></>,
};

export function Icon({ name, size = 16, className = "", ...rest }: { name: IconName; size?: number; className?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`inline-block shrink-0 ${className}`}
      aria-hidden="true"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
