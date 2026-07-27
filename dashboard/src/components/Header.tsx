import { Github } from "lucide-react";
import type { RangeKey } from "@/state/StoreProvider";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  repo: string;
  title: string;
  subtitle: string;
  /** Selector de rango (opcional; solo algunas pantallas lo muestran). */
  rangeKey?: RangeKey;
  onRangeChange?: (key: RangeKey) => void;
}

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "30d", label: "30 días" },
  { key: "60d", label: "60 días" },
  { key: "90d", label: "90 días" },
];

/** Cabecera de página: contexto del repo, rango, tema y acciones. */
export function Header({ repo, title, subtitle, rangeKey, onRangeChange }: HeaderProps) {
  const owner = repo.split("/")[0] ?? "";
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2 text-xs font-medium text-muted">
          <Github size={14} />
          {owner}
<<<<<<< HEAD
          <span className="chip ml-1 bg-accent text-bg">
            <FlaskConical size={12} />
            Simulado
          </span>
=======
>>>>>>> 09fe95a (dashboard)
        </div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
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
                  rangeKey === r.key ? "bg-accent text-bg" : "text-muted hover:text-ink"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
