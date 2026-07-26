import type { ReactNode } from "react";
import { Check } from "lucide-react";

interface PreviewCardProps {
  active: boolean;
  onClick: () => void;
  /** Mini-mockup visual de la opción (SVG/divs), no solo texto. */
  preview: ReactNode;
  label: ReactNode;
  className?: string;
}

/**
 * Bloque base para selectores "con previsualización": una tarjeta con un
 * mini-mockup arriba, una etiqueta abajo, y un check cuando está activa.
 * Usado en Apariencia (tema), severidad de comentario, rango de fechas,
 * modelo de Bedrock, etc. para que elegir una opción se sienta visual en vez
 * de leer texto plano.
 */
export function PreviewCard({ active, onClick, preview, label, className = "" }: PreviewCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`focus-ring group relative rounded-lg border p-2.5 text-left transition-colors ${
        active ? "border-accent" : "border-border hover:border-border-strong"
      } ${className}`}
    >
      {preview}
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className={`text-xs font-semibold ${active ? "text-ink" : "text-muted"}`}>{label}</span>
        {active && (
          <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-accent text-bg">
            <Check size={11} strokeWidth={3} />
          </span>
        )}
      </div>
    </button>
  );
}
