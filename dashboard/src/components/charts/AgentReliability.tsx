import { memo } from "react";
import { useTheme } from "@/state/ThemeProvider";

interface Props {
  data: { agent: string; ok: number }[];
}

/** Barras de fiabilidad por agente (% de corridas en OK). Barras HTML puras. */
export const AgentReliability = memo(function AgentReliability({ data }: Props) {
  const { p } = useTheme();
  return (
    <div className="space-y-3.5">
      {data.map((d) => {
        const color = d.ok >= 95 ? p.success : d.ok >= 85 ? p.medium : p.high;
        return (
          <div key={d.agent}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted">{d.agent}</span>
              <span className="font-semibold text-ink">{d.ok}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${d.ok}%`, background: color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
});
