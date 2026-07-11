/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Clark "Midnight Tuxedo" formal palette.
        // Token names are unchanged from the old kinetic theme so the whole app
        // re-skins from here; only the values move to the dark-navy + gold system.
        bg: "#0B0F1A", // darkest navy — structural fills (body itself is pure black)
        surface: "#1B2433", // elevated surface (panels, drawers, cards)
        muted: "#2E3A4F", // medium blue-gray — faint surfaces, dim text, icons
        "muted-foreground": "#AEB7C7", // slate-gray secondary text
        foreground: "#FFFFFF", // primary text
        "foreground-subtle": "rgba(255,255,255,0.5)", // faint labels / numerals
        accent: "#B08D57", // golden / bronze — the single primary accent
        "accent-foreground": "#0B0F1A", // near-black text on gold
        maroon: "#B7707F", // muted rose — destructive / error / stop (kept formal)
        sand: "#E9E2D0", // warm sand — paused / awaiting accents
        line: "rgba(255,255,255,0.08)", // borders are always white @ 8%
        "line-hover": "rgba(255,255,255,0.14)",
      },
      fontFamily: {
        display: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      letterSpacing: {
        tightest: "-0.03em",
      },
      transitionTimingFunction: {
        "expo-out": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      boxShadow: {
        // Soft elevation used by spotlight cards on hover.
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 50px -20px rgba(0,0,0,0.8)",
        "card-hover": "0 0 0 1px rgba(255,255,255,0.12), 0 8px 40px rgba(0,0,0,0.7), 0 0 60px rgba(176,141,87,0.10)",
        // Gold halo for primary actions (send button, active mode toggle).
        "accent-glow": "0 0 0 1px rgba(176,141,87,0.5), 0 4px 12px rgba(176,141,87,0.3), inset 0 1px 0 0 rgba(255,255,255,0.15)",
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
