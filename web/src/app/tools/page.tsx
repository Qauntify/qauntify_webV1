import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { ToolsGrid } from "@/components/tools/ToolsGrid";
import { getPublishedTools } from "@/lib/tools";

export const revalidate = 60;

export const metadata = {
  title: "ឧបករណ៍ — Qauntify",
  description:
    "EA MT5 ឥតគិតថ្លៃ indicator TradingView និងឧបករណ៍ជួញដូរផ្សេងៗពី Qauntify។",
};

export default async function ToolsPage() {
  const tools = await getPublishedTools();

  return (
    <>
      <Nav />
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
        <div className="w-full flex-1 px-4 py-8 sm:px-6 lg:px-8 xl:px-10">
          <div className="mb-8 max-w-2xl">
            <h1 className="text-3xl font-bold tracking-tight text-ink md:text-4xl">
              ឧបករណ៍
            </h1>
            <p className="mt-2 text-base text-slate">
              EA MT5 indicator TradingView និងរូបមន្តឥតគិតថ្លៃសម្រាប់បងប្អូន —
              ទាញយកឬបើកភ្ជាប់ដោយផ្ទាល់។
            </p>
          </div>
          <ToolsGrid tools={tools} />
        </div>
      </main>
      <Footer />
    </>
  );
}
