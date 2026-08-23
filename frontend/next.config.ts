import type { NextConfig } from "next";

// No reverse proxy in front of this stack (see CLAUDE.md) - the browser talks
// to Next.js only, and Next.js forwards API/MCP calls to their own containers
// over the internal compose network. That keeps the session cookie
// first-party without Caddy: the browser only ever sees one origin. It also
// means the MCP endpoint is reachable at the same origin as the web app
// (`<origin>/mcp`), which is what the settings page's generated
// `claude mcp add` command assumes.
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://django:8000";
const INTERNAL_MCP_URL = process.env.INTERNAL_MCP_URL || "http://mcp:8080";

const nextConfig: NextConfig = {
  // Produces .next/standalone so the runtime image needs no node_modules.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${INTERNAL_API_URL}/api/:path*` },
      { source: "/admin/:path*", destination: `${INTERNAL_API_URL}/admin/:path*` },
      { source: "/media/:path*", destination: `${INTERNAL_API_URL}/media/:path*` },
      { source: "/static/:path*", destination: `${INTERNAL_API_URL}/static/:path*` },
      { source: "/mcp", destination: `${INTERNAL_MCP_URL}/mcp` },
    ];
  },
};

export default nextConfig;
