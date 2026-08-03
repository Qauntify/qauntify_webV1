import { BacktestPanel } from "@/components/landing/BacktestPanel";
import { Certificates } from "@/components/landing/Certificates";
import { Hero } from "@/components/landing/Hero";
import { SignalsPreview } from "@/components/landing/SignalsPreview";
import { StatsBand } from "@/components/landing/StatsBand";
import { StrategyTesting } from "@/components/landing/StrategyTesting";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { getSignals, getStats } from "@/lib/signals";

// Signals change whenever the engine runs — read the DB on every request.
export const revalidate = 30;

export default async function Home() {
  const signals = await getSignals(3);
  const stats = await getStats();
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero latestSignal={signals[0] ?? null} />
        <div className="scroll-reveal"><StatsBand stats={stats} /></div>
        <div className="scroll-reveal"><Certificates /></div>
        <div className="scroll-reveal"><StrategyTesting /></div>
        <div className="scroll-reveal"><BacktestPanel /></div>
        <div className="scroll-reveal"><SignalsPreview signals={signals} /></div>
      </main>
      <Footer />
    </>
  );
}
