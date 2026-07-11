import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (server.js + minimal node_modules) so
  // the Docker runtime stage is small and doesn't need the full dependency tree.
  output: "standalone",
};

export default nextConfig;
