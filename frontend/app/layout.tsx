import "./globals.css";
import type { Metadata } from "next";
import dynamic from "next/dynamic";
import { Inter } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
  display: "swap",
});

// WebGL mesh-gradient background — client-only (needs WebGL, no SSR).
const MeshBackground = dynamic(() => import("@/components/ui/MeshBackground"), { ssr: false });

export const metadata: Metadata = {
  title: "Clark — General-purpose Web Agent",
  description:
    "An autonomous web agent that drives a real browser: searches, fills forms, logs in, extracts data, and saves documents — powered by Gemini AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-black font-sans">
        {/* Animated mesh-gradient background */}
        <div className="fixed inset-0 -z-10">
          <MeshBackground />
        </div>
        <div className="grid-overlay" aria-hidden="true" />
        <div className="noise" aria-hidden="true" />
        <main className="relative z-10 min-h-screen">{children}</main>
      </body>
    </html>
  );
}
