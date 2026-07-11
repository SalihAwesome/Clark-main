"use client";

import { useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "./Icon";
import type { PaymentField, ProfileField, SavedCredential } from "./types";

type Section = "info" | "payment" | "credentials";

export function ProfilePanel({
  open,
  fields,
  values,
  paymentFields,
  paymentValues,
  credentials,
  onClose,
  onSave,
  onSavePayment,
  onSaveCredential,
  onDeleteCredential,
}: {
  open: boolean;
  fields: ProfileField[];
  values: Record<string, string>;
  paymentFields: PaymentField[];
  paymentValues: Record<string, string>;
  credentials: SavedCredential[];
  onClose: () => void;
  onSave: (values: Record<string, string>) => Promise<void> | void;
  onSavePayment: (values: Record<string, string>) => Promise<void> | void;
  onSaveCredential: (cred: Partial<SavedCredential>) => Promise<void> | void;
  onDeleteCredential: (host: string) => Promise<void> | void;
}) {
  const [section, setSection] = useState<Section>("info");
  const [draft, setDraft] = useState<Record<string, string>>(values);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [detected, setDetected] = useState<string[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [card, setCard] = useState<Record<string, string>>(paymentValues);
  const [revealCard, setRevealCard] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(values); setCard(paymentValues);
      setSaved(false); setDetected(null); setRevealCard(false); setSection("info");
    }
  }, [open, values, paymentValues]);

  if (!open) return null;

  async function saveInfo() {
    setSaving(true);
    try { await onSave(draft); setSaved(true); setTimeout(() => setSaved(false), 1800); }
    finally { setSaving(false); }
  }

  async function savePayment() {
    setSaving(true);
    try { await onSavePayment(card); setSaved(true); setTimeout(() => setSaved(false), 1800); }
    finally { setSaving(false); }
  }

  function onCardChange(key: string, raw: string) {
    let v = raw;
    if (key === "card_number") v = raw.replace(/[^\d ]/g, "").slice(0, 19);
    if (key === "cvv") v = raw.replace(/\D/g, "").slice(0, 4);
    if (key === "expiry") v = raw.replace(/[^\d/]/g, "").slice(0, 5);
    setCard((c) => ({ ...c, [key]: v }));
  }

  async function uploadQID(file: File) {
    setExtracting(true);
    setDetected(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("save", "false");
      const r = await fetch("/api/profile/extract", { method: "POST", body: fd });
      const j = await r.json();
      const found: Record<string, string> = j.fields || {};
      const keys = Object.keys(found);
      if (keys.length) {
        const merged = { ...draft, ...found };
        setDraft(merged);
        await onSave(merged);
      }
      setDetected(keys);
    } catch {
      setDetected([]);
    } finally {
      setExtracting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const tab = (id: Section, icon: IconName, label: string) => (
    <button
      onClick={() => setSection(id)}
      className={`flex flex-1 items-center justify-center gap-1.5 px-2 py-2 text-[11px] font-bold uppercase tracking-tight transition-all duration-200 ease-expo-out ${
        section === id ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      <Icon name={icon} size={13} /> {label}
    </button>
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-md" onClick={onClose} />
      <aside className="animate-slide-in relative flex h-full w-full max-w-md flex-col border-s border-line bg-surface/95 backdrop-blur-xl">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <span className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.2em] text-accent"><Icon name="id-card" size={16} /> My Information</span>
          <button
            onClick={onClose}
            className="ms-auto flex h-8 w-8 items-center justify-center rounded-lg border border-line text-muted-foreground transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon"
            title="Close"
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        <div className="flex gap-0.5 border-b border-line p-1">
          {tab("info", "id-card", "My Info")}
          {tab("payment", "credit-card", "Payment")}
          {tab("credentials", "key", "Credentials")}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {section === "info" && (
            <>
              <div className="mb-5 rounded-xl border border-dashed border-line bg-bg/40 p-4">
                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-accent"><Icon name="upload" size={13} /> Upload ID</div>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  Upload a photo of your ID card and the agent will read it and fill the fields below automatically.
                </p>
                <input ref={fileRef} type="file" accept="image/*" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadQID(f); }} />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={extracting}
                  className="mt-3 w-full rounded-xl border border-accent/60 px-4 py-2.5 text-xs font-bold uppercase tracking-tight text-accent transition-all duration-200 ease-expo-out hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
                >
                  {extracting ? "Reading ID…" : "Choose ID image"}
                </button>
                {detected && (
                  <p className={`mt-2 text-[11px] ${detected.length ? "text-accent" : "text-muted-foreground"}`}>
                    {detected.length
                      ? `Detected & filled: ${detected.join(", ")}`
                      : "No fields could be read — try a clearer photo or enter them below."}
                  </p>
                )}
              </div>

              <div className="space-y-4">
                {fields.map((f) => (
                  <div key={f.key}>
                    <label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                      {f.label}
                      {f.format && <span className="ms-2 lowercase tracking-normal text-muted-foreground/60">({f.format})</span>}
                    </label>
                    <input
                      type={f.type === "date" ? "date" : f.type === "email" ? "email" : f.type === "tel" ? "tel" : "text"}
                      value={draft[f.key] || ""}
                      onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                      className="mt-1 w-full border-b border-line bg-transparent px-0 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                ))}
              </div>
            </>
          )}

          {section === "payment" && (
            <>
              <p className="mb-4 text-[11px] leading-relaxed text-muted-foreground">
                Optional. When a task needs a payment (e.g. paying a fine), the agent uses this card to fill the checkout form. Stored locally only — never sent to the AI.
              </p>
              <div className="space-y-4">
                {paymentFields.map((f) => (
                  <div key={f.key}>
                    <label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{f.label}</label>
                    <input
                      type={f.secret && !revealCard ? "password" : f.type === "tel" ? "tel" : "text"}
                      inputMode={f.key === "card_number" || f.key === "cvv" ? "numeric" : undefined}
                      autoComplete="off"
                      placeholder={f.placeholder || ""}
                      value={card[f.key] || ""}
                      onChange={(e) => onCardChange(f.key, e.target.value)}
                      className="mt-1 w-full border-b border-line bg-transparent px-0 py-2 text-sm text-foreground placeholder-muted-foreground/50 focus:border-accent focus:outline-none"
                    />
                  </div>
                ))}
              </div>
              <label className="mt-5 flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
                <input type="checkbox" checked={revealCard} onChange={(e) => setRevealCard(e.target.checked)} className="accent-accent" />
                Show card number & CVV
              </label>
              <button
                onClick={() => { setCard({}); onSavePayment({}); }}
                className="mt-4 w-full rounded-xl border border-line px-4 py-2 text-[11px] font-bold uppercase tracking-tight text-muted-foreground transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon"
              >
                Remove saved card
              </button>
            </>
          )}

          {section === "credentials" && (
            <CredentialsSection
              credentials={credentials}
              onSave={onSaveCredential}
              onDelete={onDeleteCredential}
            />
          )}
        </div>

        {section !== "credentials" && (
          <div className="flex items-center gap-2 border-t border-line px-5 py-4">
            <button
              onClick={section === "payment" ? savePayment : saveInfo}
              disabled={saving}
              className="flex-1 rounded-xl bg-accent px-4 py-3 text-sm font-bold uppercase tracking-tight text-accent-foreground transition-all duration-200 ease-expo-out hover:opacity-90 active:scale-95 disabled:opacity-50"
            >
              {saving ? "Saving…" : saved ? "Saved" : section === "payment" ? "Save Card" : "Save"}
            </button>
            <button
              onClick={onClose}
              className="rounded-xl border border-line px-4 py-3 text-sm font-bold uppercase tracking-tight text-foreground transition-all duration-200 ease-expo-out hover:border-accent/60"
            >
              Done
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

function CredentialsSection({
  credentials,
  onSave,
  onDelete,
}: {
  credentials: SavedCredential[];
  onSave: (cred: Partial<SavedCredential>) => Promise<void> | void;
  onDelete: (host: string) => Promise<void> | void;
}) {
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [edit, setEdit] = useState<Record<string, { username: string; password: string }>>({});
  const [adding, setAdding] = useState<{ url: string; username: string; password: string; label: string }>(
    { url: "", username: "", password: "", label: "" }
  );

  const rowOf = (c: SavedCredential) => edit[c.host] ?? { username: c.username, password: c.password };

  return (
    <>
      <p className="mb-4 text-[11px] leading-relaxed text-muted-foreground">
        Saved logins (like a password manager). When the agent needs to sign in to a saved site, it uses these automatically. Stored locally only — never sent to the AI.
      </p>

      {credentials.length === 0 && (
        <p className="mb-4 text-[11px] text-muted-foreground/60">
          No saved logins yet. When the agent logs you in, tick "Remember this login", or add one below.
        </p>
      )}

      <div className="space-y-3">
        {credentials.map((c) => {
          const row = rowOf(c);
          return (
            <div key={c.host} className="rounded-xl border border-line bg-bg/40 p-3">
              <div className="flex items-center gap-2">
                <span className="truncate text-[12px] font-bold text-foreground" title={c.url}>{c.label || c.host}</span>
                <span className="ms-auto shrink-0 text-[10px] text-muted-foreground/50">{c.host}</span>
              </div>
              <input
                value={row.username}
                placeholder="username"
                autoComplete="off"
                onChange={(e) => setEdit((s) => ({ ...s, [c.host]: { ...row, username: e.target.value } }))}
                className="mt-2 w-full border-b border-line bg-transparent px-0 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none"
              />
              <div className="mt-1 flex items-center gap-2">
                <input
                  type={reveal[c.host] ? "text" : "password"}
                  value={row.password}
                  placeholder="password"
                  autoComplete="off"
                  onChange={(e) => setEdit((s) => ({ ...s, [c.host]: { ...row, password: e.target.value } }))}
                  className="w-full border-b border-line bg-transparent px-0 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none"
                />
                <button
                  onClick={() => setReveal((r) => ({ ...r, [c.host]: !r[c.host] }))}
                  className="shrink-0 text-[10px] uppercase text-muted-foreground hover:text-accent"
                  title="Show / Hide"
                >
                  {reveal[c.host] ? "Hide" : "Show"}
                </button>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => onSave({ host: c.host, url: c.url, label: c.label, username: row.username, password: row.password })}
                  className="flex-1 rounded-lg bg-accent px-3 py-2 text-[11px] font-bold uppercase tracking-tight text-accent-foreground transition-all duration-200 ease-expo-out hover:opacity-90 active:scale-95"
                >
                  Save
                </button>
                <button
                  onClick={() => onDelete(c.host)}
                  className="rounded-lg border border-line px-3 py-2 text-[11px] font-bold uppercase tracking-tight text-muted-foreground transition-all duration-200 ease-expo-out hover:border-maroon hover:text-maroon"
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 rounded-xl border border-dashed border-line bg-bg/40 p-3">
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-accent"><Icon name="plus" size={13} /> Add a login</div>
        {(["url", "username", "password", "label"] as const).map((k) => (
          <input
            key={k}
            type={k === "password" ? "password" : "text"}
            placeholder={k === "url" ? "site url (e.g. https://example.com)" : k === "label" ? "label (optional)" : k}
            autoComplete="off"
            value={adding[k]}
            onChange={(e) => setAdding((a) => ({ ...a, [k]: e.target.value }))}
            className="mt-2 w-full border-b border-line bg-transparent px-0 py-1.5 text-sm text-foreground placeholder-muted-foreground/50 focus:border-accent focus:outline-none"
          />
        ))}
        <button
          onClick={async () => {
            if (!adding.url.trim() || !adding.username.trim()) return;
            await onSave(adding);
            setAdding({ url: "", username: "", password: "", label: "" });
          }}
          className="mt-3 w-full rounded-xl border border-accent/60 px-4 py-2 text-[11px] font-bold uppercase tracking-tight text-accent transition-all duration-200 ease-expo-out hover:bg-accent hover:text-accent-foreground"
        >
          Add login
        </button>
      </div>
    </>
  );
}
