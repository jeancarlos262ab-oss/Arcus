import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTheme } from "@/state/ThemeProvider";
import type { TimePoint } from "@/lib/selectors";
import { ChartTooltip } from "./ChartTooltip";

interface Props {
  data: TimePoint[];
}

/** Área apilada de hallazgos por severidad a lo largo del tiempo. */
export function FindingsOverTime({ data }: Props) {
  const { p } = useTheme();

  if (data.length === 0) {
    return <p className="py-16 text-center text-sm text-muted">Sin datos en el rango.</p>;
  }

  const series = [
    { key: "low", name: "Baja", color: p.low },
    { key: "medium", name: "Media", color: p.medium },
    { key: "high", name: "Alta", color: p.high },
  ] as const;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.5} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={p.border} vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: p.faint, fontSize: 11 }}
          axisLine={{ stroke: p.border }}
          tickLine={false}
          minTickGap={28}
        />
        <YAxis
          tick={{ fill: p.faint, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<ChartTooltip />} />
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stackId="1"
            stroke={s.color}
            fill={`url(#grad-${s.key})`}
            strokeWidth={2}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
