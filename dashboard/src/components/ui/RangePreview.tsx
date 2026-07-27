import type { RangeKey } from "@/state/StoreProvider";

/**
 * Formas de sparkline fijas (no datos reales) que solo comunican "cuántos
 * puntos caben" en cada rango: 30 días se ve más espaciado/agudo, 90 días más
 * denso y suavizado. Sirve como pista visual, no como gráfica exacta.
 */
const SHAPES: Record<RangeKey, number[]> = {
  "30d": [4, 9, 5, 11, 6, 3, 8],
  "60d": [3, 7, 5, 9, 6, 8, 4, 10, 6, 5, 8, 4],
  "90d": [2, 5, 4, 7, 5, 8, 6, 9, 7, 10, 8, 11, 9, 7, 10],
};

const ACCENT = "#8B5CF6";

function toPoints(values: number[], w: number, h: number): string {
  const max = Math.max(...values);
  const step = w / (values.length - 1);
  return values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`)
    .join(" ");
}

/** Mini sparkline SVG representando la densidad de datos de un rango. */
function MiniSparkline({ range, active }: { range: RangeKey; active: boolean }) {
  const w = 56;
  const h = 24;
  const points = toPoints(SHAPES[range], w, h);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={active ? "currentColor" : ACCENT}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface RangePreviewButtonProps {
  range: RangeKey;
  label: string;
  active: boolean;
  onClick: () => void;
}

/**
 * Botón compacto del selector de rango con una mini-sparkline arriba de la
 * etiqueta. Pensado para el Header (fila angosta), no usa `PreviewCard`
 * (que es más alto/cuadrado) sino un formato horizontal más discreto.
 */
export function RangePreviewButton({ range, label, active, onClick }: RangePreviewButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`focus-ring flex flex-col items-center gap-0.5 rounded-md px-2.5 py-1.5 transition-colors ${
        active ? "bg-accent text-bg" : "text-muted hover:text-ink"
      }`}
    >
      <MiniSparkline range={range} active={active} />
      <span className="text-[0.68rem] font-semibold">{label}</span>
    </button>
  );
}
