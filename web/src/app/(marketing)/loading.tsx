export default function MarketingLoading() {
  return (
    <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
      <div className="animate-pulse page-container space-y-8 py-8" aria-hidden>
        <div className="space-y-3">
          <div className="h-9 w-48 rounded bg-line/70" />
          <div className="h-4 w-full max-w-xl rounded bg-line/50" />
        </div>
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
    </main>
  );
}
