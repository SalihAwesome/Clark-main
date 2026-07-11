"use client";

import { MeshGradient } from "@paper-design/shaders-react";

/**
 * Clark animated background: a WebGL mesh-gradient shader in the Midnight Tuxedo
 * palette, held at 40% opacity over a pure-black base, with three slow pulsing
 * blur blobs (gold + blue-gray) for soft, ambient lighting. Mounted client-side
 * only (dynamic import with ssr:false) since it needs WebGL.
 */
export default function MeshBackground() {
  return (
    <div className="absolute inset-0 h-full w-full overflow-hidden bg-black">
      <MeshGradient
        className="absolute inset-0 h-full w-full opacity-40"
        colors={["#0B0F1A", "#1B2433", "#2E3A4F", "#B08D57"]}
        speed={0.6}
        distortion={0.85}
        swirl={0.55}
      />

      {/* Ambient lighting blobs (gold / blue-gray, kept at 1.5–3%) */}
      <div className="pointer-events-none absolute inset-0">
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
      </div>

      {/* Vignette so content stays legible toward the edges */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(120% 120% at 50% 30%, transparent 40%, rgba(0,0,0,0.55) 100%)" }}
      />
    </div>
  );
}
