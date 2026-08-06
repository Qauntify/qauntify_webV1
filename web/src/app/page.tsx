import { Certificates } from "@/components/landing/Certificates";
import { Features } from "@/components/landing/Features";
import { Hero } from "@/components/landing/Hero";
import { SignalsPreview } from "@/components/landing/SignalsPreview";
import { StrategyTesting } from "@/components/landing/StrategyTesting";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { getSignals, getStats } from "@/lib/signals";

export const revalidate = 30;

export default async function Home() {
  const signals = await getSignals(3);
  const stats = await getStats();
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero stats={stats} />
        <Features />
        <Certificates />
        <StrategyTesting />
        <SignalsPreview signals={signals} />
      </main>
      <Footer />
    </>
  );
}
