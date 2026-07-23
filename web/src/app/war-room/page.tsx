import { SectionHeader } from "@/components/shared/SectionHeader";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { DebateBoard } from "@/components/war-room/DebateBoard";
import { WarRoomStage } from "@/components/war-room/WarRoomStage";
import { getDebates } from "@/lib/debates";

// Debates land as the engine confirms signals — read fresh-ish.
export const revalidate = 20;

export default async function WarRoom() {
  const debates = await getDebates(8);
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="section-block">
          <div className="page-container py-16 md:py-20">
            <SectionHeader
              eyebrow="AI War Room"
              title="Three robots debate. The Manager decides."
              subtitle="For every confirmed signal, a Technical analyst and a Fundamental analyst argue their case, then a Manager makes the final call. This shows the AI's reasoning as a conversation — for illustration only, not financial advice."
            />
            <div className="mt-10 space-y-8">
              {debates.length === 0 ? (
                <DebateBoard debates={[]} />
              ) : (
                <>
                  <WarRoomStage debate={debates[0]} />
                  {debates.length > 1 ? (
                    <DebateBoard debates={debates.slice(1)} />
                  ) : null}
                </>
              )}
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
