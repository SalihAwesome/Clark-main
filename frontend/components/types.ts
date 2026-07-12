export type TraceStep =
  | { type: "thought"; content: string }
  | { type: "action"; tool: string; input: Record<string, unknown> }
  | { type: "observation"; tool: string; result: Record<string, unknown> }
  | { type: "screenshot"; url: string; page_url?: string; title?: string }
  | { type: "awaiting_user"; reason: string; kind?: string; image?: string }
  | { type: "stopped"; content: string }
  | { type: "error"; content: string };

// A saved conversation (audit trail) summary, for the History panel.
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;            // completed | paused | stopped | in_progress
  track?: string;
  surface?: string;
  mode?: string;             // "agent" | "chat"
  num_steps?: number;
  num_actions?: number;
  final?: string;
}

export interface AuditEvent {
  type: string;
  ts?: string;
  [key: string]: unknown;
}

export interface AuditRecord extends ConversationSummary {
  prompts: string[];
  transcript: AuditEvent[];
}

export type Track = string;    // general-purpose — no longer scoped to specific sectors
export type Surface = "web";    // desktop surface was removed with the Electron app

// A field the agent asks the user for mid-task (e.g. QID, Date of Birth).
export interface InfoField {
  key: string;
  label: string;
  type?: string;     // text | email | tel | date | select | checkbox | radio
  format?: string;   // e.g. yyyy/mm/dd
  placeholder?: string;
  value?: string;    // current value (used to pre-fill the "edit" form)
  name?: string;     // form field name (kind === "edit"); key mirrors it
  options?: string[] | null;  // for select fields (kind === "edit")
}

// A field in the "Saved Information" profile panel.
export interface ProfileField {
  key: string;
  label: string;
  type?: string;
  format?: string;
}

// A field in the "Payment Card" panel (optional, stored locally only).
export interface PaymentField {
  key: string;
  label: string;
  type?: string;
  secret?: boolean;     // masked in the UI (card number / CVV)
  placeholder?: string;
}

// A saved login in the "My Credentials" panel (Chrome-style, local only).
export interface SavedCredential {
  host: string;
  url: string;
  username: string;
  password: string;
  label: string;
}

// Human-in-the-loop prompt surfaced to the user during an agent run.
export interface Pending {
  reason: string;
  kind?: string;                       // "login" | "credentials" | "confirm" | "info" | "captcha" | "otp" | "review" | "edit"
  fields?: (string | InfoField)[];
  image?: string;                      // captcha image (base64 data URL), when kind === "captcha"
  details?: {                          // structured details to show, e.g. for kind === "review"
    total_fees?: string;
    address?: { label: string; value: string }[];
    title?: string;                    // section heading for the details table (e.g. "Delivery Options")
    email?: string;
    raw?: string;
  };
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  trace?: TraceStep[];
  files?: { name: string; bytes: number }[];
}
