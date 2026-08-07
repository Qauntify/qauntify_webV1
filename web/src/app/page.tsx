import { Certificates } from "@/components/landing/Certificates";
import { Features } from "@/components/landing/Features";
import { Hero } from "@/components/landing/Hero";
import { SignalsPreview } from "@/components/landing/SignalsPreview";
import { StrategyTesting } from "@/components/landing/StrategyTesting";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { getDailyPnLStats, getSignals, getStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";

export const revalidate = 30;

export default async function Home() {
  const token = serviceRoleToken();
  const [signals, stats, dailyPnL] = await Promise.all([
    getSignals(3),
    getStats(),
    // Locked to the current month on the homepage (no year/month nav there)
    // -- 35 days covers this month plus the prior-month padding days the
    // grid shows, no need for the full year /track-record fetches.
    getDailyPnLStats(token, 35),
  ]);
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero stats={stats} />
        <Features dailyPnL={dailyPnL} />
        <Certificates />
        <StrategyTesting />
        <SignalsPreview signals={signals} />
      </main>
      <Footer />
    </>
  );
}
