import type { RepoHealthSummary } from "@/lib/selectors";

function healthColor(score: number): string {
  if (score >= 75) return "#2DBF89";
  if (score >= 50) return "#F59E0B";
  return "#F43F81";
}

interface RepoPreviewCardProps {
  name: string;
  summary?: RepoHealthSummary;
  active: boolean;
  onClick: () => void;
}

/**
 * Fila de repositorio para el selector del sidebar: un punto de color según
 * su "health score" (últimos 30 días) en vez de un color fijo neutro/accent,
 * para dar una pista real de qué repo necesita atención sin agregar ruido
 * visual (sigue siendo una sola línea de texto).
 */
export function RepoPreviewCard({ name, summary, active, onClick }: RepoPreviewCardProps) {
  const score = summary?.healthScore ?? null;
  const dotColor = active ? "var(--accent)" : score === null ? "var(--faint)" : healthColor(score);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={score === null ? "Sin revisiones todavía" : `Salud: ${score}%`}
      className={`focus-ring flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
        active ? "bg-accent/10 font-semibold text-accent" : "text-muted hover:bg-surface-2 hover:text-ink"
      }`}
    >
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: dotColor, opacity: score === null && !active ? 0.5 : 1 }}
      />
      <span className="truncate">{name}</span>
    </button>
  );
}
