import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the Docker runtime image (Phase 10) — traces the minimal
  // node_modules subset into .next/standalone instead of shipping the full install.
  output: "standalone",
};

export default nextConfig;
