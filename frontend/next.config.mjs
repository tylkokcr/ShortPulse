/** @type {import('next').NextConfig} */

// Backend port, overridable via frontend/.env.local (see .env.local.example).
// Keep in sync with lib/api.ts, which uses the same variable for the
// WebSocket connection — the rewrite below only proxies /api/*.
const BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT ?? "8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${BACKEND_PORT}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
