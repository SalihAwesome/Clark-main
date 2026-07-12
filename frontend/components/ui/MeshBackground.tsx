"use client";

import { MeshGradient } from "@paper-design/shaders-react";

/**
 * Clark animated background: a WebGL mesh-gradient shader in the Clay & Cotton
 * palette, held at 40% opacity over the warm paper base, with three slow pulsing
 * blur blobs (terracotta + teal) for soft, ambient warmth. Mounted client-side
 * only (dynamic import with ssr:false) since it needs WebGL.
 */
export default function MeshBackground() {
  return (
    <div className="absolute inset-0 h-full w-full overflow-hidden bg-bg">
      <MeshGradient
        className="absolute inset-0 h-full w-full opacity-40"
        colors={["#C96A4D", "#D4973A", "#3B8E8C", "#F7F4EE"]}
        speed={0.6}
        distortion={0.85}
        swirl={0.55}
      />

      {/* Ambient lighting blobs (terracotta / teal, kept at 3–5%) */}
      <div className="pointer-events-none absolute inset-0">
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
      </div>

      {/* Soft vignette so content stays legible toward the edges */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(120% 120% at 50% 30%, transparent 40%, rgba(44,40,38,0.25) 100%)" }}
      />
    </div>
  );
}
