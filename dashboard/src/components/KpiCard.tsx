import { memo } from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string;
  icon: LucideIcon;
  /** Texto del delta, p. ej. "+3 vs. periodo previo". Omitir si no aplica. */
  delta?: string;
  /** Dirección del delta: define color e ícono. */
  trend?: "up" | "down" | "flat";
  /** Si true, un delta "up" es bueno (verde). Si false, "up" es malo (rojo). */
  upIsGood?: boolean;
  accent?: boolean;
}

/** Tarjeta de métrica principal (KPI). */
export const KpiCard = memo(function KpiCard({
  label,
  value,
  icon: Icon,
  delta,
  trend = "flat",
  upIsGood = true,
  accent = false,
}: KpiCardProps) {
  const good =
    trend === "flat" ? null : (trend === "up") === upIsGood;
  const deltaColor =
    good === null ? "text-faint" : good ? "text-success" : "text-high";
  const DeltaIcon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;

  return (
    <div className={`panel animate-fade-up p-4 ${accent ? "border-l-2 border-l-accent" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-[0.72rem] font-semibold uppercase tracking-wider text-muted">
          {label}
        </span>
        <span className="grid h-8 w-8 place-items-center rounded-md bg-ink text-bg">
          <Icon size={15} strokeWidth={2.2} />
        </span>
      </div>
      <div className="mt-2.5 text-2xl font-extrabold tracking-tight text-ink">{value}</div>
      {delta && (
        <div className={`mt-1.5 flex items-center gap-1 text-xs font-semibold ${deltaColor}`}>
          <DeltaIcon size={14} />
          {delta}
        </div>
      )}
    </div>
  );
});
