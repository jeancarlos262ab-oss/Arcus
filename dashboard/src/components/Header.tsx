import { FlaskConical, Github, Plus } from "lucide-react";
import type { RangeKey } from "@/state/StoreProvider";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  repo: string;
  title: string;
  subtitle: string;
  /** Selector de rango (opcional; solo algunas pantallas lo muestran). */
  rangeKey?: RangeKey;
  onRangeChange?: (key: RangeKey) => void;
  /** Acción "Nueva revisión" (opcional). */
  onNewReview?: () => void;
}

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "30d", label: "30 días" },
  { key: "60d", label: "60 días" },
  { key: "90d", label: "90 días" },
];

/** Cabecera de página: contexto del repo, rango, tema y acciones. */
export function Header({
  repo,
  title,
  subtitle,
  rangeKey,
  onRangeChange,
  onNewReview,
}: HeaderProps) {
  const owner = repo.split("/")[0] ?? "";
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2 text-xs font-medium text-muted">
          <Github size={14} />
          {owner}
          <span className="chip ml-1 border border-accent/35 bg-accent/10 text-accent">
            <FlaskConical size={12} />
            Simulado
          </span>
        </div>
        <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-ink">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        {rangeKey && onRangeChange && (
          <div className="flex rounded-lg border border-border bg-surface p-1">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => onRangeChange(r.key)}
                className={`focus-ring rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  rangeKey === r.key ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
        <ThemeToggle />
        {onNewReview && (
          <button onClick={onNewReview} className="btn-primary">
            <Plus size={16} />
            Nueva revisión
          </button>
        )}
      </div>
    </header>
  );
}
