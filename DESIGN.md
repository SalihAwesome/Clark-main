---
name: Clark — Web Agent
description: A warm, playful, general-purpose autonomous web agent
colors:
  primary: "#C96A4D"
  primary-deep: "#B05439"
  primary-subtle: "#F5E4DC"
  accent: "#3B8E8C"
  accent-deep: "#2E7371"
  accent-subtle: "#D6EDEC"
  cta: "#D4973A"
  cta-subtle: "#F5E8D0"
  neutral-bg: "#F7F4EE"
  neutral-surface: "#EFE8DE"
  neutral-surface-raised: "#E0D6C8"
  neutral-ink: "#2C2826"
  neutral-ink-subtle: "#7A7069"
  neutral-line: "rgba(44,40,38,0.10)"
  negative: "#C4554A"
  positive: "#5C8C6E"
  dark-bg: "#1C1816"
  dark-surface: "#2B2521"
  dark-surface-raised: "#3C3430"
  dark-ink: "#ECE6E0"
  dark-ink-subtle: "#9C928C"
  dark-line: "rgba(236,230,224,0.10)"
typography:
  display:
    fontFamily: "Nunito, var(--font-nunito), system-ui, sans-serif"
    fontSize: "clamp(2rem, 5vw, 4rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Nunito, var(--font-nunito), system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "normal"
  title:
    fontFamily: "Inter, var(--font-inter), system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Inter, var(--font-inter), system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, var(--font-inter), system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  full: "9999px"
  lg: "12px"
  md: "10px"
  sm: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  xxl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#FFFFFF"
    rounded: "{rounded.full}"
    padding: "12px 28px"
    typography: "{typography.title}"
  button-primary-hover:
    backgroundColor: "{colors.accent-deep}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.lg}"
    padding: "10px 22px"
    border: "1.5px solid {colors.neutral-line}"
  button-cta:
    backgroundColor: "{colors.cta}"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.full}"
    padding: "12px 32px"
  card:
    backgroundColor: "{colors.neutral-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "#FFFFFF"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.md}"
    padding: "10px 14px"
    border: "1.5px solid {colors.neutral-line}"
  input-focus:
    border: "1.5px solid {colors.accent}"
---
# Design System: Clark — The Playful Companion

## 1. Overview

**Creative North Star: "The Playful Companion"**

Clark is an autonomous web agent that does the work so you don't have to — navigating pages, filling forms, searching, and reporting back. The design wraps that capable engine in a warm, playful interface that feels like working with a friend rather than operating machinery. It occupies the space between "delightful companion" and "trustworthy assistant," never tipping into cold corporate tool or generic AI chatbot.

The system explicitly rejects the dark terminal aesthetic, navy-and-gold "Midnight Tuxedo" formality, SaaS dashboard clichés, and the purple-teal gradient AI look. Instead it anchors in warm terracotta clay, soft cream surfaces, and a cool teal accent for interactive moments — like a favorite café where you get things done.

**Key Characteristics:**
- Warm and approachable — color leads, cold edges are forbidden
- Playful without being childish — rounded corners, friendly typography, purposeful micro-interactions
- Dual-mode native — light and dark modes share the same warm DNA, not inversions of a cold theme
- General-audience first — no developer jargon, no terminal references, no assumed tech comfort
- Crafted intentionality — every spacing, animation, and micro-copy choice carries purpose

## 2. Colors: The Clay & Cotton Palette

The palette is anchored by **Baked Clay** (terracotta), which carries warmth across surfaces, headers, and active states. **Lagoon** (teal) is the interactive accent — reserved for buttons, links, and state indicators — so its rarity signals action. **Honey Gold** (amber) punctuates high-value CTAs. Neutral surfaces range from warm cream paper in light mode to warm charcoal in dark mode, never cooling into grey or navy.

### Light Mode

- **Warm Paper** (`#F7F4EE` / oklch(0.97 0.012 70)): body background. A warm cream that reads as paper, not terminal.
- **Toasted Cream** (`#EFE8DE` / oklch(0.93 0.018 75)): default surface for cards, panels, drawers.
- **Warm Linen** (`#E0D6C8` / oklch(0.88 0.022 80)): raised surface for hovered cards, active drawers.
- **Baked Clay** (`#C96A4D` / oklch(0.55 0.16 38)): primary brand color, used for headers, hero elements, decorative surfaces.
- **Terracotta Dusk** (`#B05439` / oklch(0.47 0.17 34)): hover/active state of the primary.
- **Clay Mist** (`#F5E4DC` / oklch(0.92 0.025 50)): tinted surface alerts, soft primary backgrounds.
- **Lagoon** (`#3B8E8C` / oklch(0.55 0.10 195)): interactive accent — buttons, links, active indicators.
- **Deep Teal** (`#2E7371` / oklch(0.46 0.11 195)): hover state for interactive elements.
- **Lagoon Mist** (`#D6EDEC` / oklch(0.92 0.025 190)): tinted backgrounds for info/teal sections.
- **Honey Gold** (`#D4973A` / oklch(0.65 0.12 72)): high-value CTA highlights, gold callouts.
- **Honey Mist** (`#F5E8D0` / oklch(0.93 0.03 80)): tinted gold backgrounds.
- **Warm Charcoal** (`#2C2826` / oklch(0.20 0.01 60)): primary body text.
- **Warm Stone** (`#7A7069` / oklch(0.48 0.02 65)): secondary text, placeholders (4.5:1 against bg).
- **Warm Mist** (`rgba(44,40,38,0.10)`): borders and dividers.
- **Rose Clay** (`#C4554A` / oklch(0.54 0.14 28)): error/stop states.
- **Moss** (`#5C8C6E` / oklch(0.55 0.08 155)): success states.

### Dark Mode

- **Warm Dark** (`#1C1816` / oklch(0.15 0.01 55)): body background. A warm near-black, not grey or navy.
- **Toasted Dark** (`#2B2521` / oklch(0.22 0.015 60)): surface for cards, panels, drawers.
- **Warm Slate** (`#3C3430` / oklch(0.30 0.015 60)): raised surface.
- **Baked Clay** and **Lagoon** carry through at the same OKLCH lightness (0.55) for consistency; the darker background provides enough contrast.
- **Dark Ink** (`#ECE6E0` / oklch(0.92 0.008 65)): body text on dark.
- **Dark Ink Subtle** (`#9C928C` / oklch(0.62 0.015 60)): secondary text.

### Named Rules

**The Play-Don't-Tell Rule.** Teal (Lagoon) is the interactive accent — used for buttons, links, and active states only. If a teal element isn't clickable or currently active, it's teal for the wrong reason. Terracotta carries warmth; teal carries action.

**The Honey Spotlight Rule.** Gold-amber (Honey) is reserved for high-signal CTAs — no more than one per viewport. Overuse dulls its urgency.

## 3. Typography

**Display Font:** Nunito (with system-ui fallback) — a warm, rounded sans-serif for headings. Its open, friendly letterforms carry the playful personality without sacrificing readability.

**Body Font:** Inter (with system-ui fallback) — the workhorse sans for UI labels, messages, data, and all body copy. Clean, dense, and familiar at small sizes.

**Character:** The pairing works because the fonts are different by design — Inter is crisp and geometric (sharp terminals, precise spacing), Nunito is rounded and humanist (soft terminals, warm apertures). They contrast on the warmth axis while sharing the same x-height and even spacing cadence.

### Hierarchy

- **Display** (Nunito 700, `clamp(2rem, 5vw, 4rem)`, 1.05, -0.02em): Hero headings and brand statements only. Never used for UI labels. `text-wrap: balance` applied.
- **Headline** (Nunito 600, 1.5rem, 1.15): Section titles, panel headers, dialog titles. `text-wrap: balance` applied.
- **Title** (Inter 600, 1.125rem, 1.25): Card headers, button labels, field labels.
- **Body** (Inter 400, 0.9375rem, 1.6): All prose, messages, descriptions. Max line length 72ch.
- **Label** (Inter 500, 0.75rem, 1, 0.06em tracking): Captions, badges, metadata, step numbers. Uppercase only when the context calls for hierarchy (step labels, status badges).

### Named Rules

**The One Family Rule for UI. Inter owns everything below headline level. Nunito never appears in body copy, buttons, labels, or data. The switch to Nunito at precisely the headline boundary ensures users feel the warmth without losing legibility at small sizes.**

## 4. Elevation

Depth comes from warm tonal stacking and soft ambient shadows — not aggressive drop shadows or glossy reflections. The system uses a hybrid approach: surfaces differentiate through value shifts (lighter in light mode, darker in dark mode), and a restrained shadow vocabulary adds lift where hierarchy demands it.

In light mode, surfaces step from Warm Paper (body) → Toasted Cream (default surface) → Warm Linen (raised). The shifts are subtle (0.04–0.05 L in OKLCH) — enough to differentiate, not enough to feel stacked. Shadows use warm-tinted blacks (`rgba(44,40,38, α)`) rather than neutral or cool blacks.

In dark mode, the same layering uses Warm Dark → Toasted Dark → Warm Slate, with shadows at `rgba(0,0,0,0.4)` with a warm tint.

The card-spotlight radial effect (a soft gradient highlight following the cursor) uses the Baked Clay hue at low opacity, not the cold gold of the prior system.

### Shadow Vocabulary

- **Ambient Soft** (`0 2px 8px rgba(44,40,38,0.06)`): Default card shadow. Subtle lift without sharp edges.
- **Ambient Raised** (`0 4px 16px rgba(44,40,38,0.08), 0 1px 3px rgba(44,40,38,0.06)`): Hovered cards, dialog surfaces, dropdowns.
- **Ambient Modal** (`0 8px 32px rgba(44,40,38,0.12), 0 2px 8px rgba(44,40,38,0.08)`): Modal dialogs, maximized panels.
- **Accent Glow** (`0 0 0 2px rgba(59,142,140,0.3), 0 0 20px rgba(59,142,140,0.15)`): Focus ring for interactive elements (teal).

### Named Rules

**The Flat-At-Rest Rule.** Shadows appear as a response to state (hover, focus, elevation change), not as a default identity. Cards at rest have no shadow — only tonal layering differentiates them from the body.

## 5. Components

### Brand Mark (ClarkMark)

A rounded-square icon container (12px radius) with a subtle warm surface gradient, housing a simplified letter silhouette: a circle enclosing a path that reads as a stylized "C". The icon sits adjacent to the wordmark — "Cl" in body weight, "ark" in the Baked Clay primary. Below, "Web Agent" in 9px uppercase with wide tracking. The mark is compact (34px default) and sits in the top-left of every view.

### Buttons

- **Shape:** Primary buttons are fully rounded (rounded-full, 9999px) — the roundness reads as friendly. Secondary and ghost buttons use rounded-lg (12px) for a slightly more crafted, less aggressive feel.
- **Send (Primary Action):** Baked Clay (light mode) / Lagoon (dark mode) background, white text, full-round. Hover shifts to the deep variant with a `translateY(-1px)` lift in 200ms expo-out. A subtle inner highlight (0.5px white at 15% opacity on the top edge) gives the button a gentle lit quality.
- **Stop (Destructive):** Outline style with Rose Clay stroke and text. A small pulsing dot animation indicates active/interruptible state.
- **Ghost / Secondary:** Transparent background, Warm Charcoal text, rounded-lg. Hover gets a 12% warm tint fill. No outline at rest; a subtle warm line appears on focus.
- **CTA (Honey):** Honey Gold background, Warm Charcoal text, full-round. Reserved for the primary action on hero or modal surfaces.

All buttons use `cubic-bezier(0.16, 1, 0.3, 1)` (expo-out) for transitions. Hover transitions are 200ms. Motion is disabled under `prefers-reduced-motion`.

### Inputs / Command Bar

- **Style:** White (light) / Toasted Dark (dark) background with a 1.5px Warm Mist border. 10px radius. Inner padding 10px 14px.
- **Focus:** Border shifts to Lagoon teal with the accent glow shadow ring. Transition in 200ms expo-out.
- **Placeholder:** Warm Stone / Dark Ink Subtle at 4.5:1 contrast (not the typical muted-gray failure).
- **Command Bar:** The primary input (text prompt for the agent) is visually emphasized — wider padding, a slightly larger type size (Inter 500 at 1rem), and the Send button nested inside the right edge. A subtle warm inner glow on focus.

### Cards

- **Corner Style:** 12px radius (rounded-lg). Soft and friendly without being pill-shaped.
- **Background:** Toasted Cream (light) / Toasted Dark (dark) — differentiated from body by tonal shift, not shadow.
- **Shadow Strategy:** No shadow at rest; Ambient Soft on hover.
- **Border:** None by default. An optional warm hairline (`1px solid neutral-line`) for cards that sit on tinted surfaces.
- **Internal Padding:** 24px (lg) as default. Quick-action cards use 20px.
- **Card Spotlight:** On hover, a radial gradient at the cursor position (Baked Clay at 10% → transparent) provides a warm glow — the successor to the old gold-spotlight effect.

### Navigation Bar (Top)

A fixed top bar, 56px tall, containing the Clark wordmark on the left and icon actions (history, profile, settings) on the right. Background matches the surface (Toasted Cream / Toasted Dark) with a 1px bottom border in Warm Mist. Icons are 18–20px inline SVG in Warm Charcoal / Dark Ink. No background color fill — the bar reads as the top of the content column.

### Drawers (Profile Panel, History Panel)

A slide-in panel from the right edge, 380px wide, surface background (Toasted Cream / Toasted Dark). Header includes a title and close icon. Content sections are separated by 1px Warm Mist dividers with generous 24px padding. The drawer sits above an 80%-opacity warm black scrim. In dark mode, the scrim is `rgba(28,24,22,0.85)` — not neutral black.

### Live Preview (Browser Frame)

A rounded (12px) viewport showing the agent's browser, framed by a subtle warm border. The frame has a faux-browser chrome treatment at the top: a small dot cluster (close/minimize/maximize) in warm tones, and a URL bar showing the current page. The frame background uses a soft warm gradient when no page is loaded.

### Marquee

An infinite horizontal ticker of capability keywords. Border-top and border-bottom at 1px Warm Mist. Background uses a 30%-opacity Toasted Cream tint, shifting to Baked Clay fill with white text for the "inverted" variant. Items are 11px uppercase with generous tracking, separated by a small star glyph in Lagoon. Animation: 30s (default) or 16s (fast) linear scroll. Stopped under `prefers-reduced-motion`.

### Markdown Content

Agent answers and chat messages are rendered as safe React nodes (no `dangerouslySetInnerHTML`). The markdown uses the body typography scale. Inline code uses Inter at 0.85em with a `rgba(44,40,38,0.06)` warm tint background. Block quotes get a 3px Baked Clay left border. Links are Lagoon teal with a 1px underline offset at 2px.

### Human-in-the-Loop Gates (Modals)

Modal dialogs for credentials, OTP, captcha, and payment review. They use the Ambient Modal shadow and surface background. A soft teal accent ring on the CTA button draws attention to the action. The modal title uses the Headline scale. Input fields match the standard input style. A "Cancel" ghost button (Warm Stone text) always accompanies the primary action.

## 6. Do's and Don'ts

### Do:
- **Do** use Baked Clay (terracotta) for decorative surfaces, hero sections, and background warmth — it carries the brand.
- **Do** reserve Lagoon (teal) exclusively for interactive elements: buttons, links, active indicators, focus rings.
- **Do** use Honey Gold for exactly one high-value CTA per surface. Its rarity is its power.
- **Do** use tonal layering (value shifts) as the primary depth cue; shadows are secondary.
- **Do** apply `text-wrap: balance` on display and headline text; `text-wrap: pretty` on body prose.
- **Do** keep body line length capped at 72ch.
- **Do** respect `prefers-reduced-motion` — all looping animations stop; all hover transitions become instant.
- **Do** maintain 4.5:1 contrast on all body text including placeholders. The Warm Stone secondary text is deliberately calibrated to hit this against the Warm Paper background.

### Don't:
- **Don't** use cold navy, pure black, or cool greys as surface backgrounds — that's the Midnight Tuxedo system being replaced.
- **Don't** use teal decoratively. If it's teal and not clickable or active, it's wrong.
- **Don't** replicate the SaaS dark-dashboard look — no glassmorphism, no purple/teal gradients, no glowing metric cards.
- **Don't** use Nunito in body copy, labels, buttons, or data. Inter owns everything below headline level.
- **Don't** use display fonts on UI labels, buttons, or table data. Product register rule: display voices are for display moments only.
- **Don't** use gradient text (`background-clip: text` with a gradient). Single solid colors only for text emphasis.
- **Don't** use side-stripe borders (`border-left` > 1px as a colored accent on cards or calls-to-action).
- **Don't** use glassmorphism as a default decorative treatment — no frosted-glass panels unless the pattern genuinely needs it.
- **Don't** animate layout properties (width, height, top, margin). Use transform and opacity only.
- **Don't** use modals as a first thought — exhaust inline and progressive alternatives first.
- **Don't** put `01 / 02 / 03` numbered markers above every section as default scaffolding. Numbers only when the content is a real sequence.
