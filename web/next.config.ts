import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep soft-navigated pages warm in the client router so back/forward and
  // revisiting admin tabs feel instant instead of refetching immediately.
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
};

export default nextConfig;
