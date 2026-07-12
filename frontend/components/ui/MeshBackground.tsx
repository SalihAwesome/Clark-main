"use client";

import { useEffect, useState } from "react";
import { MeshGradient } from "@paper-design/shaders-react";

/**
 * Clark animated background: a WebGL mesh-gradient shader.
 *
 * Light mode — Clay & Cotton palette (warm cream, terracotta, teal).
 * Dark mode — Midnight Tuxedo palette (pure black, navy, gold).
 *
 * Swaps palette and vignette colour based on .dark class on <html>.
 * Mounted client-side only (dynamic import with ssr:false) since it needs WebGL.
 */
export default function MeshBackground() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
    const obs = new MutationObserver(() =>
      setDark(document.documentElement.classList.contains("dark"))
    );
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return (
    <div className={`absolute inset-0 h-full w-full overflow-hidden ${dark ? "bg-black" : "bg-[#F7F4EE]"}`}>
      <MeshGradient
        className="absolute inset-0 h-full w-full opacity-40"
        colors={
          dark
            ? ["#0B0F1A", "#1B2433", "#2E3A4F", "#B08D57"]
            : ["#C96A4D", "#D4973A", "#3B8E8C", "#F7F4EE"]
        }
        speed={0.6}
        distortion={0.85}
        swirl={0.55}
      />

      {/* Ambient lighting blobs */}
      <div className="pointer-events-none absolute inset-0">
        {dark ? (
          <>
            <div
              className="absolute left-1/3 top-1/4 h-72 w-72 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "6s", backgroundColor: "rgba(176, 141, 87, 0.03)" }}
            />
            <div
              className="absolute bottom-1/3 right-1/4 h-64 w-64 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "8s", animationDelay: "1s", backgroundColor: "rgba(46, 58, 79, 0.04)" }}
            />
            <div
              className="absolute right-1/3 top-1/2 h-56 w-56 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "10s", animationDelay: "0.5s", backgroundColor: "rgba(176, 141, 87, 0.02)" }}
            />
          </>
        ) : (
          <>
            <div
              className="absolute left-1/3 top-1/4 h-72 w-72 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "6s", backgroundColor: "rgba(201, 106, 77, 0.05)" }}
            />
            <div
              className="absolute bottom-1/3 right-1/4 h-64 w-64 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "8s", animationDelay: "1s", backgroundColor: "rgba(59, 142, 140, 0.04)" }}
            />
            <div
              className="absolute right-1/3 top-1/2 h-56 w-56 animate-pulse rounded-full blur-3xl"
              style={{ animationDuration: "10s", animationDelay: "0.5s", backgroundColor: "rgba(212, 151, 58, 0.03)" }}
            />
          </>
        )}
      </div>

      {/* Soft vignette so content stays legible toward the edges */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: dark
            ? "radial-gradient(120% 120% at 50% 30%, transparent 40%, rgba(0,0,0,0.55) 100%)"
            : "radial-gradient(120% 120% at 50% 30%, transparent 40%, rgba(44,40,38,0.25) 100%)",
        }}
      />
    </div>
  );
}
