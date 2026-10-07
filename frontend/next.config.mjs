import createNextIntlPlugin from "next-intl/plugin";

/** @type {import('next').NextConfig} */

// Where this server proxies /api/* to. A host, not just a port: in a
// container the backend is a different machine, so `localhost` is this
// container and finds nothing. Compose sets BACKEND_ORIGIN=http://api:8000.
//
// Read at request time on the server, so it is *not* NEXT_PUBLIC_ and never
// reaches the browser — the browser only ever talks to this origin.
const BACKEND_ORIGIN =
  process.env.BACKEND_ORIGIN ?? `http://localhost:${process.env.NEXT_PUBLIC_BACKEND_PORT ?? "8000"}`;

const nextConfig = {
  // Emits a self-contained server bundle with only the node_modules it
  // actually imports, which is what makes the runtime image small enough
  // to be worth shipping — the full node_modules here is ~500MB.
  output: "standalone",

  experimental: {
    // The /api rewrite below buffers request bodies, and by default only
    // the first 10MB. In production Caddy sends /api straight to the
    // backend and never touches this, but a self-hosted install without
    // Caddy — and local development — goes through it, and every upload
    // past 10MB arrived cut off: a 200MB video, or a beat edit's clips.
    // Sized to the largest body the backend accepts: a beat edit's 2GB of
    // clips plus its track (MAX_BEAT_EDIT_MB).
    proxyClientMaxBodySize: "2100mb",
  },

  async rewrites() {
    return [
      {
        // The render-progress WebSocket. Next's rewrites don't proxy
        // upgrades, which is why lib/api.ts connects to the backend
        // directly — see NEXT_PUBLIC_WS_ORIGIN there for the deployed case.
        source: "/api/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

// Points next-intl at i18n/request.ts, which is how a server component
// gets the right catalogue without every page passing one down.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

export default withNextIntl(nextConfig);
