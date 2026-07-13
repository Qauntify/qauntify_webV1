export default function AdminLoading() {
  return (
    <div className="animate-pulse space-y-6" aria-hidden>
      <div className="space-y-2">
        <div className="h-7 w-40 rounded bg-line/70" />
        <div className="h-4 w-72 max-w-full rounded bg-line/50" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="stat-tile min-h-[5.5rem]">
            <div className="h-3 w-20 rounded bg-line/60" />
            <div className="mt-3 h-8 w-24 rounded bg-line/70" />
          </div>
        ))}
      </div>
    </div>
  );
}
