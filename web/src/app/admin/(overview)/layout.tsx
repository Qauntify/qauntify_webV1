import { OverviewSubNav } from "@/components/admin/OverviewSubNav";

export default function AdminOverviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <h1 className="text-2xl font-bold">Overview</h1>
      <p className="mt-1 text-sm text-slate">
        Engine health, member stats, and daily closed-trade calendar.
      </p>
      <OverviewSubNav />
      <div className="mt-8 w-full">{children}</div>
    </>
  );
}
