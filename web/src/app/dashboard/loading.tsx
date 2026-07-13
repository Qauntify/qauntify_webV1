export default function DashboardLoading() {
  return (
    <div className="animate-pulse space-y-8 p-4 lg:p-6" aria-hidden>
      <div className="h-8 w-48 rounded bg-line/70" />
      <div className="grid gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg border border-line bg-card" />
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-40 rounded-xl border border-line bg-card" />
        ))}
      </div>
    </div>
  );
}
