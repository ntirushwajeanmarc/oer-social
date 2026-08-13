import type { NextConfig } from "next";

// Server-side proxy target. In Docker Compose this is http://api:8000.
const backend = (process.env.BACKEND_URL || "http://localhost:8000").replace(
  /\/$/,
  ""
);

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/media/:path*", destination: `${backend}/media/:path*` },
    ];
  },
};

export default nextConfig;
