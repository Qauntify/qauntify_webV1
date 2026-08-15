import type { NextConfig } from "next";

// Chart images (chart_url / outcome_chart_url) are served from Supabase
// Storage's public bucket, so next/image needs the project host allow-listed.
const supabaseHost = process.env.NEXT_PUBLIC_SUPABASE_URL
  ? new URL(process.env.NEXT_PUBLIC_SUPABASE_URL).hostname
  : undefined;

const nextConfig: NextConfig = {
  // Keep soft-navigated pages warm in the client router so back/forward and
  // revisiting admin tabs feel instant instead of refetching immediately.
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
  images: {
    remotePatterns: supabaseHost
      ? [
          {
            protocol: "https",
            hostname: supabaseHost,
            pathname: "/storage/v1/object/**",
          },
        ]
      : [],
  },
};

export default nextConfig;
