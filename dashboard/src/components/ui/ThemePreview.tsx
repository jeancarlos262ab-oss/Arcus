import type { ThemeMode } from "@/lib/theme";
import { PreviewCard } from "./PreviewCard";

/**
 * Colores fijos (no CSS vars) para que cada mini-preview se vea igual sin
 * importar el tema activo: el recuadro "Claro" siempre debe verse claro,
 * el "Oscuro" siempre oscuro, aunque la app entera esté en el otro modo.
 */
const SWATCH = {
  light: { bg: "#F7F9FB", surface: "#FFFFFF", border: "#DFE3E9", ink: "#181F2A", muted: "#5A6472" },
  dark: { bg: "#0D1117", surface: "#161B22", border: "#2A313C", ink: "#E6EDF3", muted: "#8B949E" },
};
const ACCENT = "#8B5CF6";

interface ThemePreviewCardProps {
  mode: ThemeMode;
  label: string;
  active: boolean;
  onClick: () => void;
}

/** Mini-mockup de la interfaz (sidebar + contenido) para el modo dado. */
function MiniMockup({ variant }: { variant: "light" | "dark" }) {
  const c = SWATCH[variant];
  return (
    <div
      className="flex h-20 w-full overflow-hidden rounded-md border"
      style={{ background: c.bg, borderColor: c.border }}
    >
      {/* Sidebar */}
      <div
        className="flex w-1/3 flex-col gap-1.5 border-r p-2"
        style={{ background: c.surface, borderColor: c.border }}
      >
        <div className="h-2 w-2 rounded-sm" style={{ background: ACCENT }} />
        <div className="h-1 w-full rounded-full" style={{ background: c.border }} />
        <div className="h-1 w-3/4 rounded-full" style={{ background: c.border }} />
        <div className="h-1 w-full rounded-full" style={{ background: c.border }} />
      </div>
      {/* Contenido */}
      <div className="flex flex-1 flex-col gap-1.5 p-2">
        <div className="h-1.5 w-2/3 rounded-full" style={{ background: c.ink, opacity: 0.85 }} />
        <div className="h-1 w-1/2 rounded-full" style={{ background: c.muted, opacity: 0.7 }} />
        <div className="mt-1 grid grid-cols-3 gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-5 rounded-sm border"
              style={{ background: c.surface, borderColor: c.border }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Mockup combinado claro+oscuro en diagonal, para representar el modo "Sistema". */
function SystemMockup() {
  return (
    <div className="relative h-20 w-full overflow-hidden rounded-md border border-border-strong">
      <div className="absolute inset-0 [clip-path:polygon(0_0,100%_0,0_100%)]">
        <MiniMockup variant="light" />
      </div>
      <div className="absolute inset-0 [clip-path:polygon(100%_0,100%_100%,0_100%)]">
        <MiniMockup variant="dark" />
      </div>
    </div>
  );
}

/** Tarjeta de opción de tema con previsualización visual + check de selección. */
export function ThemePreviewCard({ mode, label, active, onClick }: ThemePreviewCardProps) {
  return (
    <PreviewCard
      active={active}
      onClick={onClick}
      label={label}
      preview={mode === "system" ? <SystemMockup /> : <MiniMockup variant={mode} />}
    />
  );
}
