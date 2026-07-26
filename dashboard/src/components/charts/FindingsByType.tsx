import { memo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { typeColor, TYPE_LABEL } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import type { FindingType } from "@/lib/types";
import { ChartTooltip } from "./ChartTooltip";

interface Props {
  totals: Record<FindingType, number>;
}

/** Barras horizontales de hallazgos por tipo. */
export const FindingsByType = memo(function FindingsByType({ totals }: Props) {
  const { p } = useTheme();
  const data = (Object.keys(totals) as FindingType[])
    .map((t) => ({ type: t, label: TYPE_LABEL[t], value: totals[t] }))
    .sort((a, b) => b.value - a.value);

  if (!data.some((d) => d.value > 0)) {
    return <p className="py-10 text-center text-sm text-muted">Sin hallazgos en el rango.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
        barCategoryGap={12}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={p.border} horizontal={false} />
        <XAxis
          type="number"
          tick={{ fill: p.faint, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: p.muted, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={96}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(128,128,128,0.08)" }} />
        <Bar dataKey="value" name="Hallazgos" radius={[0, 6, 6, 0]} maxBarSize={22}>
          {data.map((d) => (
            <Cell key={d.type} fill={typeColor(p, d.type)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});
