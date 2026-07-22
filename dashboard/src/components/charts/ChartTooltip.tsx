import type { TooltipProps } from "recharts";

/** Tooltip corporativo compartido por todas las gráficas. */
export function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-border-strong bg-surface-2 px-3 py-2 shadow-lift">
      {label != null && (
        <div className="mb-1 text-xs font-semibold text-ink">{String(label)}</div>
      )}
      <div className="space-y-0.5">
        {payload.map((entry, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: entry.color ?? entry.payload?.fill }}
            />
            <span className="text-muted">{entry.name}</span>
            <span className="ml-auto font-semibold text-ink">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
