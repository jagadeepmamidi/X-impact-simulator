import type { NextConfig } from "next";

const backend = process.env.INTERNAL_API_URL || `http://127.0.0.1:${process.env.BACKEND_PORT || 8000}`;

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
