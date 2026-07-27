import { memo } from "react";
import { useTheme } from "@/state/ThemeProvider";

interface Props {
  /** `ok` es null cuando no hay corridas: no hay pipeline que medir. */
  data: { agent: string; ok: number | null }[];
}

/** Barras de fiabilidad por agente (% de corridas en OK). Barras HTML puras. */
export const AgentReliability = memo(function AgentReliability({ data }: Props) {
  const { p } = useTheme();
  return (
    <div className="space-y-3.5">
      {data.map((d) => {
        const ok = d.ok;
        const hasData = ok !== null;
        const color = !hasData ? p.faint : ok >= 95 ? p.success : ok >= 85 ? p.medium : p.high;
        return (
          <div key={d.agent}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted">{d.agent}</span>
              <span className="font-semibold text-ink">{hasData ? `${ok}%` : "–"}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: hasData ? `${ok}%` : "0%", background: color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
});
