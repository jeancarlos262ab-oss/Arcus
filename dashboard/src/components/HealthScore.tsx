import { memo } from "react";
import { useTheme } from "@/state/ThemeProvider";

interface HealthScoreProps {
  score: number; // 0-100
}

/** Anillo de puntaje de salud del repo (SVG puro, adaptado al tema). */
export const HealthScore = memo(function HealthScore({ score }: HealthScoreProps) {
  const { p } = useTheme();
  const size = 128;
  const center = size / 2;
  const radius = 50;
  const stroke = 10;
  const circ = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circ - (clamped / 100) * circ;

  const color = clamped >= 75 ? p.success : clamped >= 50 ? p.medium : p.high;
  const label = clamped >= 75 ? "Saludable" : clamped >= 50 ? "Aceptable" : "Necesita atención";

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={p.border}
            strokeWidth={stroke}
          />
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            transform={`rotate(-90 ${center} ${center})`}
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-extrabold tracking-tight text-ink">{clamped}</span>
          <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-faint">
            / 100
          </span>
        </div>
      </div>
      <span className="mt-2 text-sm font-semibold" style={{ color }}>
        {label}
      </span>
    </div>
  );
});
