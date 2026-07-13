export default function OverviewSectionLoading() {
  return (
    <div className="animate-pulse space-y-4" aria-hidden>
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
