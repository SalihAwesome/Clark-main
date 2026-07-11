/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enable standalone output for Docker: produces a self-contained build
  // in .next/standalone with all required dependencies.
  output: "standalone",

  // Proxy API calls to the FastAPI backend during development so the frontend
  // can call /api/* without CORS or hard-coded hosts.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8008";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
module.exports = nextConfig;
