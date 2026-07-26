import { memo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { severityColor, SEVERITY_LABEL } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import type { Severity } from "@/lib/types";
import { ChartTooltip } from "./ChartTooltip";

interface Props {
  totals: Record<Severity, number>;
}

/** Donut de distribución por severidad con total al centro. */
export const SeverityDonut = memo(function SeverityDonut({ totals }: Props) {
  const { p } = useTheme();
  const data = (["high", "medium", "low"] as Severity[])
    .map((s) => ({ name: SEVERITY_LABEL[s], value: totals[s], key: s }))
    .filter((d) => d.value > 0);
  const total = data.reduce((s, d) => s + d.value, 0);

  if (total === 0) {
    return <p className="py-10 text-center text-sm text-muted">Sin hallazgos en el rango.</p>;
  }

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Tooltip content={<ChartTooltip />} />
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={62}
            outerRadius={92}
            paddingAngle={2}
            stroke="none"
          >
            {data.map((d) => (
              <Cell key={d.key} fill={severityColor(p, d.key)} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-extrabold text-ink">{total}</span>
        <span className="text-[0.68rem] font-semibold uppercase tracking-wider text-faint">
          hallazgos
        </span>
      </div>
      <div className="mt-3 flex justify-center gap-4">
        {data.map((d) => (
          <div key={d.key} className="flex items-center gap-1.5 text-xs text-muted">
            <span className="h-2 w-2 rounded-full" style={{ background: severityColor(p, d.key) }} />
            {d.name}
            <span className="font-semibold text-ink">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
});
