/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Clark "Clay & Cotton" warm palette.
        // Light mode: warm cream paper base, terracotta primary, teal accent.
        // Dark mode: warm charcoal base, same primaries adjusted for contrast.
        bg: "#F7F4EE", // Warm Paper — body background
        surface: "#EFE8DE", // Toasted Cream — cards, panels, drawers
        "surface-raised": "#E0D6C8", // Warm Linen — hovered/active surfaces
        muted: "#7A7069", // Warm Stone — secondary text, placeholders
        "muted-foreground": "#7A7069", // alias for backwards compat
        foreground: "#2C2826", // Warm Charcoal — primary text
        "foreground-subtle": "rgba(44,40,38,0.45)",
        accent: "#3B8E8C", // Lagoon — interactive: buttons, links, active states
        "accent-foreground": "#FFFFFF", // white text on teal
        "accent-deep": "#2E7371", // Deep Teal — hover state for interactive
        primary: "#C96A4D", // Baked Clay — decorative surfaces, headers, warmth
        "primary-deep": "#B05439", // Terracotta Dusk — hover state
        "primary-subtle": "#F5E4DC", // Clay Mist — tinted backgrounds
        maroon: "#C4554A", // Rose Clay — error / stop / destructive
        cta: "#D4973A", // Honey Gold — high-value CTA only
        "cta-subtle": "#F5E8D0", // Honey Mist
        sand: "#D6EDEC", // Lagoon Mist — info/teal tinted backgrounds
        line: "rgba(44,40,38,0.10)", // Warm Mist — borders
        "line-hover": "rgba(44,40,38,0.18)",
        // Dark mode overrides — "Midnight Tuxedo" (the original Clark aesthetic:
        // pure-black body, navy surfaces, gold accent, applied via .dark on <html>)
        "dark-bg": "#000000", // Pure black — body background
        "dark-surface": "#1B2433", // Deep Navy — cards, panels, drawers
        "dark-surface-raised": "#2A3850", // Raised Navy — hovered/active surfaces
        "dark-foreground": "#ECE6E0", // Dark Ink
        "dark-foreground-subtle": "rgba(236,230,224,0.4)",
        "dark-muted": "#AEB7C7", // Slate-gray — secondary text
        "dark-line": "rgba(255,255,255,0.08)",
        "dark-line-hover": "rgba(255,255,255,0.14)",
        "dark-accent": "#B08D57", // Gold — accent in dark mode
        "dark-accent-foreground": "#0B0F1A", // Navy text on gold
      },
      fontFamily: {
        display: ["var(--font-nunito)", "Nunito", "system-ui", "sans-serif"],
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      letterSpacing: {
        tightest: "-0.03em",
        wide: "0.06em",
      },
      transitionTimingFunction: {
        "expo-out": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      boxShadow: {
        // Warm-toned ambient shadows
        card: "0 2px 8px rgba(44,40,38,0.06)",
        "card-hover": "0 4px 16px rgba(44,40,38,0.08), 0 1px 3px rgba(44,40,38,0.06)",
        modal: "0 8px 32px rgba(44,40,38,0.12), 0 2px 8px rgba(44,40,38,0.08)",
        // Teal accent glow for focus rings
        "accent-glow":
          "0 0 0 2px rgba(59,142,140,0.3), 0 0 20px rgba(59,142,140,0.15)",
        // Gold CTA glow
        "cta-glow":
          "0 0 0 2px rgba(212,151,58,0.3), 0 0 20px rgba(212,151,58,0.15)",
      },
      keyframes: {
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(24px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateX(10px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        marquee: "marquee 30s linear infinite",
        "marquee-fast": "marquee 16s linear infinite",
        "fade-up": "fade-up 0.6s cubic-bezier(0.16,1,0.3,1) both",
        "scale-in": "scale-in 0.3s cubic-bezier(0.16,1,0.3,1) both",
        "slide-in": "slide-in 0.35s cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};
