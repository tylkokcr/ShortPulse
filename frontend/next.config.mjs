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

export default nextConfig;
