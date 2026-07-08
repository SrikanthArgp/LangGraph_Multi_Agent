import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Two build targets share this config: Phase 10's Docker Compose deployment (a real Node
  // server via `.next/standalone` — see frontend/Dockerfile's `COPY .next/standalone` +
  // `CMD node server.js`) and Phase 15's S3/CloudFront static deployment (`out/`, no server
  // at request time — see enterprize-deploy-steps.md Stage A step 5). Defaults to
  // "standalone" so Phase 10 keeps working unchanged; the Phase 15 build opts in explicitly
  // via NEXT_OUTPUT_MODE=export.
  output: process.env.NEXT_OUTPUT_MODE === "export" ? "export" : "standalone",
};

export default nextConfig;
