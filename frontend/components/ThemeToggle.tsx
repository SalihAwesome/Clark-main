"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";

/**
 * Reads the intended theme from localStorage (or OS preference) and applies it
 * to <html> — shared between the anti-flash script and hydration effect.
 */
function applyStoredTheme() {
  try {
    const t = localStorage.getItem("theme");
    const preferDark = t === "dark" || (t !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", preferDark);
    document.documentElement.style.colorScheme = preferDark ? "dark" : "light";
    return preferDark;
  } catch {
    return false;
  }
}

/**
 * Theme toggle — switches between light/warm (the current "Clay & Cotton" UI) and
 * dark/"Midnight Tuxedo" (the original Clark aesthetic: black/navy with gold accents).
 *
 * Persists the user's choice in localStorage (`theme: "light" | "dark"`). On first
 * visit, respects the OS-level `prefers-color-scheme`.
 */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  // Re-apply from localStorage on mount (guards against React hydration stripping
  // the .dark class that the anti-flash script added to <html>).
  useEffect(() => {
    setDark(applyStoredTheme());
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    document.documentElement.style.colorScheme = next ? "dark" : "light";
    localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button
      onClick={toggle}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="group flex h-9 w-9 items-center justify-center rounded-lg border border-line text-muted-foreground transition-all duration-200 ease-expo-out hover:border-accent/60 hover:text-accent dark:border-dark-line dark:text-dark-muted dark:hover:border-dark-accent/60 dark:hover:text-dark-accent"
    >
      {dark ? (
        <Icon name="sun" size={15} className="transition-transform duration-300 group-hover:scale-110 group-hover:text-[#d4973a]" />
      ) : (
        <Icon name="moon" size={15} className="transition-transform duration-300 group-hover:scale-110 group-hover:text-accent" />
      )}
    </button>
  );
}
