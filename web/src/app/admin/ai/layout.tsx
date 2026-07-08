import { AiSubNav } from "@/components/admin/AiSubNav";

export default function AdminAiLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <h1 className="text-2xl font-bold">AI</h1>
      <p className="mt-2 text-sm text-slate">
        Configure how the engine scans markets and review every SEA-LION
        response from recent runs.
      </p>
      <AiSubNav />
      <div className="mt-8 w-full">{children}</div>
    </>
  );
}
