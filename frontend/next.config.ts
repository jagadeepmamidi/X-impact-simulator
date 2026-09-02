import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    if (process.env.VERCEL) return [];
    const backend = process.env.INTERNAL_API_URL || `http://127.0.0.1:${process.env.BACKEND_PORT || 8000}`;
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
