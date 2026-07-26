/** Placeholder ligero mientras se descarga el chunk de una página (lazy loading). */
export function PageSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="h-3 w-24 rounded bg-surface-2" />
          <div className="mt-2 h-8 w-56 rounded bg-surface-2" />
        </div>
        <div className="h-9 w-32 rounded-lg bg-surface-2" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel h-28 p-5">
            <div className="h-full w-full rounded-lg bg-surface-2" />
          </div>
        ))}
      </div>
      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel h-64 p-5 lg:col-span-2">
          <div className="h-full w-full rounded-lg bg-surface-2" />
        </div>
        <div className="panel h-64 p-5">
          <div className="h-full w-full rounded-lg bg-surface-2" />
        </div>
      </div>
    </div>
  );
}
