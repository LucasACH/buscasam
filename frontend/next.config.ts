import type { NextConfig } from "next";
import path from "node:path";

const backendUrl = process.env.BUSCASAM_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["192.168.*.*", "*.trycloudflare.com"],
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
