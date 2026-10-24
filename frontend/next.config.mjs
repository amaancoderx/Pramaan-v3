/** @type {import('next').NextConfig} */
const defaultBackend = process.env.RENDER ? "https://pramaan-api.onrender.com" : "http://127.0.0.1:8000";
const rawBackend = process.env.BACKEND_URL || defaultBackend;
// Render passes a bare host ("pramaan-api.onrender.com"); add the scheme.
const backendUrl = rawBackend.startsWith("http") ? rawBackend.replace(/\/$/, "") : `https://${rawBackend}`;
if ((process.env.VERCEL || process.env.RENDER) && !process.env.BACKEND_URL) {
  console.warn(`[Pramaan] BACKEND_URL not set. Defaulting to ${backendUrl}. Set BACKEND_URL in Render Environment settings to match your pramaan-api URL.`);
}

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  images: { unoptimized: true },
  // OCR on a slow CPU can take a while; the default 30 s proxy timeout is too tight.
  experimental: { proxyTimeout: 120_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
