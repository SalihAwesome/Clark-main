import "./globals.css";
import type { Metadata } from "next";
import dynamic from "next/dynamic";
import { Inter, Nunito } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
  display: "swap",
});

const nunito = Nunito({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-nunito",
  display: "swap",
});

// WebGL mesh-gradient background — client-only (needs WebGL, no SSR).
const MeshBackground = dynamic(() => import("@/components/ui/MeshBackground"), { ssr: false });

export const metadata: Metadata = {
  icons: [
    { rel: "icon", url: "/favicon.svg", type: "image/svg+xml" },
    { rel: "apple-touch-icon", url: "/logo.png" },
  ],
  title: "Clark — General-purpose Web Agent",
  description:
    "An autonomous web agent that drives a real browser: searches, fills forms, logs in, extracts data, and saves documents — powered by AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${nunito.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{
          __html: `
            try {
              var t = localStorage.getItem("theme");
              var isDark = t === "dark" || (t !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
              document.documentElement.classList.toggle("dark", isDark);
              document.documentElement.style.colorScheme = isDark ? "dark" : "light";
            } catch(e) {}
          `
        }} />
      </head>
      <body className="min-h-screen bg-[#F7F4EE] font-sans text-[#2C2826] dark:bg-black dark:text-white">
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
