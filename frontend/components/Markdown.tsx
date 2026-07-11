"use client";

import type { ReactNode } from "react";

/**
 * Tiny, dependency-free Markdown renderer for CHAT-mode answers.
 *
 * It builds React elements (never dangerouslySetInnerHTML), so there's no XSS surface, and it needs
 * no `npm install` — it just works after a frontend restart. Handles the common cases Clark
 * produces: headings, bold/italic, inline code, fenced code blocks, links, ordered/unordered lists,
 * blockquotes, horizontal rules, and paragraphs (single newlines become <br/>).
 */

// ── inline: `code`, [links](url), **bold**, _italic_ ─────────────────────────
function parseInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Order matters: code first (so we never format inside code), then links, bold, italic.
  const pattern =
    /(`[^`]+`)|(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\s][^*]*\*)|(_[^_\s][^_]*_)/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-i${i++}`;
    if (tok.startsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-foreground/10 px-1.5 py-0.5 font-mono text-[13px]">
          {tok.slice(1, -1)}
        </code>
      );
    } else if (tok.startsWith("[")) {
      const mm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok);
      if (mm) {
        nodes.push(
          <a key={key} href={mm[2]} target="_blank" rel="noopener noreferrer"
             className="text-accent underline underline-offset-2 hover:opacity-80">
            {mm[1]}
          </a>
        );
      } else {
        nodes.push(tok);
      }
    } else if (tok.startsWith("**") || tok.startsWith("__")) {
      nodes.push(<strong key={key} className="font-bold text-foreground">{tok.slice(2, -2)}</strong>);
    } else {
      nodes.push(<em key={key} className="italic">{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const isFence = (l: string) => /^\s*```/.test(l);
const isHeading = (l: string) => /^(#{1,6})\s+/.test(l);
const isUl = (l: string) => /^\s*[-*+]\s+/.test(l);
const isOl = (l: string) => /^\s*\d+[.)]\s+/.test(l);
const isQuote = (l: string) => /^\s*>\s?/.test(l);
const isHr = (l: string) => /^\s*([-*_])\1\1+\s*$/.test(l);

// ── GFM tables ───────────────────────────────────────────────────────────────
const splitRow = (l: string): string[] => {
  let s = l.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
};
// The "| --- | :--: |" separator under a table header.
const isTableSep = (l: string): boolean => {
  if (!l || !l.includes("|")) return false;
  const cells = splitRow(l);
  return cells.length >= 1 && cells.every((c) => /^:?-{1,}:?$/.test(c));
};
const ALIGN: Record<string, string> = { left: "text-left", right: "text-right", center: "text-center" };

export function Markdown({ content, className = "" }: { content: string; className?: string }) {
  const blocks: ReactNode[] = [];
  const lines = (content || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block: ``` … ```
    if (isFence(line)) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !isFence(lines[i])) { buf.push(lines[i]); i++; }
      i++; // skip closing fence
      blocks.push(
        <pre key={key++}
             className="my-2 overflow-x-auto rounded-xl border border-line bg-foreground/5 p-3 font-mono text-[13px] leading-relaxed text-foreground">
          <code>{buf.join("\n")}</code>
        </pre>
      );
      continue;
    }

    if (line.trim() === "") { i++; continue; }

    // Heading
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const sizes = ["text-xl", "text-lg", "text-base", "text-base", "text-sm", "text-sm"];
      const Tag = `h${Math.min(level, 6)}` as keyof JSX.IntrinsicElements;
      blocks.push(
        <Tag key={key++} className={`mb-1 mt-3 font-bold text-foreground ${sizes[level - 1]}`}>
          {parseInline(h[2], `h${key}`)}
        </Tag>
      );
      i++;
      continue;
    }

    // GFM table: a "| a | b |" header line immediately followed by a "| --- | --- |" separator.
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      const aligns = splitRow(lines[i + 1]).map((c) => {
        const l = c.startsWith(":"), r = c.endsWith(":");
        return l && r ? "center" : r ? "right" : "left";
      });
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "" &&
             !isFence(lines[i]) && !isHeading(lines[i])) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      const tkey = key++;
      blocks.push(
        <div key={tkey} className="my-3 overflow-x-auto rounded-xl border border-line">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line bg-foreground/[0.06]">
                {header.map((c, ci) => (
                  <th key={ci} className={`whitespace-nowrap px-3 py-2 font-bold uppercase tracking-tight text-foreground ${ALIGN[aligns[ci]] || "text-left"}`}>
                    {parseInline(c, `th${tkey}-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-line/40 last:border-0 even:bg-foreground/[0.02]">
                  {header.map((_, ci) => (
                    <td key={ci} className={`px-3 py-2 align-top text-foreground/90 ${ALIGN[aligns[ci]] || "text-left"}`}>
                      {parseInline(r[ci] ?? "", `td${tkey}-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Horizontal rule
    if (isHr(line)) { blocks.push(<hr key={key++} className="my-3 border-line" />); i++; continue; }

    // Blockquote
    if (isQuote(line)) {
      const buf: string[] = [];
      while (i < lines.length && isQuote(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      blocks.push(
        <blockquote key={key++} className="my-2 border-l-2 border-accent pl-3 text-muted-foreground">
          {parseInline(buf.join(" "), `q${key}`)}
        </blockquote>
      );
      continue;
    }

    // Unordered list
    if (isUl(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && isUl(lines[i])) {
        const n = items.length;
        items.push(<li key={n} className="ml-1">{parseInline(lines[i].replace(/^\s*[-*+]\s+/, ""), `ul${key}-${n}`)}</li>);
        i++;
      }
      blocks.push(<ul key={key++} className="my-2 list-disc space-y-1 pl-5 marker:text-accent">{items}</ul>);
      continue;
    }

    // Ordered list
    if (isOl(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && isOl(lines[i])) {
        const n = items.length;
        items.push(<li key={n} className="ml-1">{parseInline(lines[i].replace(/^\s*\d+[.)]\s+/, ""), `ol${key}-${n}`)}</li>);
        i++;
      }
      blocks.push(<ol key={key++} className="my-2 list-decimal space-y-1 pl-5 marker:text-muted-foreground">{items}</ol>);
      continue;
    }

    // Paragraph: gather consecutive plain lines (single newlines → <br/>).
    const buf: string[] = [];
    while (
      i < lines.length && lines[i].trim() !== "" &&
      !isFence(lines[i]) && !isHeading(lines[i]) && !isUl(lines[i]) &&
      !isOl(lines[i]) && !isQuote(lines[i]) && !isHr(lines[i]) &&
      !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))  // don't swallow a table
    ) {
      buf.push(lines[i]); i++;
    }
    const para: ReactNode[] = [];
    buf.forEach((ln, idx) => {
      if (idx > 0) para.push(<br key={`br${key}-${idx}`} />);
      para.push(...parseInline(ln, `p${key}-${idx}`));
    });
    blocks.push(<p key={key++} className="leading-relaxed">{para}</p>);
  }

  return (
    <div className={`space-y-1 text-[15px] text-foreground ${className}`} dir="ltr">
      {blocks}
    </div>
  );
}
