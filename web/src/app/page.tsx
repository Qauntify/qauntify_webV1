import { Faq } from "@/components/landing/Faq";
import { Features } from "@/components/landing/Features";
import { Hero } from "@/components/landing/Hero";
import { Markets } from "@/components/landing/Markets";
import { Pricing } from "@/components/landing/Pricing";
import { SignalsPreview } from "@/components/landing/SignalsPreview";
import { StatsBand } from "@/components/landing/StatsBand";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { getSignals, getStats } from "@/lib/signals";

// Signals change whenever the engine runs — read the DB on every request.
export const dynamic = "force-dynamic";

export default async function Home() {
  const signals = await getSignals(3);
  const stats = await getStats();
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero latestSignal={signals[0] ?? null} />
        <div className="scroll-reveal"><StatsBand stats={stats} /></div>
        <div className="scroll-reveal"><Features /></div>
        <div className="scroll-reveal"><SignalsPreview signals={signals} /></div>
        <div className="scroll-reveal"><Markets /></div>
        <div className="scroll-reveal"><Pricing /></div>
        <div className="scroll-reveal"><Faq /></div>
      </main>
      <Footer />
    </>
  );
}
