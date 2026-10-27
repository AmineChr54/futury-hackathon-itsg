import type { NextConfig } from "next";

// The Python pipeline server (pipeline/server.py). Next owns `/`; every other path
// (/demo/, /pipeline, /api/*, /v1/*) falls through to it.
const PIPELINE = process.env.PIPELINE_URL ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return { beforeFiles: [], afterFiles: [], fallback: [{ source: "/:path*", destination: `${PIPELINE}/:path*` }] };
  },
};

export default nextConfig;
