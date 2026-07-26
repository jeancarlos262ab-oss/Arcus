import { MessageSquare } from "lucide-react";
import type { Severity } from "@/lib/types";
import { PreviewCard } from "./PreviewCard";

/** Colores fijos (no CSS vars) para que el mockup no cambie con el tema activo. */
const SEVERITY_COLOR: Record<Severity, string> = {
  high: "#F43F81",
  medium: "#F59E0B",
  low: "#6385FF",
};
const ORDER: Severity[] = ["high", "medium", "low"];

interface SeverityThresholdCardProps {
  threshold: Severity;
  label: string;
  active: boolean;
  onClick: () => void;
}

/**
 * Mini-mockup de un comentario de PR: muestra las 3 franjas de severidad y
 * "apaga" (atenúa) las que quedarían por debajo del umbral elegido, para que
 * se entienda de un vistazo qué hallazgos sí generarían comentario.
 */
function MiniCommentMockup({ threshold }: { threshold: Severity }) {
  // "low" = todas comentan; "medium" = media y alta; "high" = solo alta.
  const included = (s: Severity) => ORDER.indexOf(s) <= ORDER.indexOf(threshold);

  return (
    <div className="rounded-md border border-border bg-bg p-2">
      <div className="mb-1.5 flex items-center gap-1.5 text-[0.62rem] font-semibold text-faint">
        <MessageSquare size={10} />
        Comentario en el PR
      </div>
      <div className="space-y-1">
        {ORDER.map((s) => {
          const on = included(s);
          return (
            <div key={s} className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: on ? SEVERITY_COLOR[s] : "var(--border-strong)" }}
              />
              <span
                className="h-1.5 rounded-full"
                style={{
                  width: s === "high" ? "70%" : s === "medium" ? "55%" : "40%",
                  background: on ? SEVERITY_COLOR[s] : "var(--border)",
                  opacity: on ? 0.9 : 0.5,
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Tarjeta de opción de umbral de severidad con previsualización del efecto en el comentario. */
export function SeverityThresholdCard({ threshold, label, active, onClick }: SeverityThresholdCardProps) {
  return (
    <PreviewCard
      active={active}
      onClick={onClick}
      label={label}
      preview={<MiniCommentMockup threshold={threshold} />}
    />
  );
}
