/**
 * Paletas de color en JS para claro/oscuro.
 *
 * Los componentes con clases Tailwind usan las CSS variables de `index.css`.
 * Pero Recharts y el SVG necesitan cadenas de color reales; para eso consumen
 * `useTheme().p` (Palette), que corresponde al tema activo.
 *
 * Mantener en sync con las variables de `index.css`.
 */

import type { AgentStatus, FindingType, Severity } from "./types";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export interface Palette {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  borderStrong: string;
  ink: string;
  muted: string;
  faint: string;
  accent: string;
  accentHover: string;
  high: string;
  medium: string;
  low: string;
  success: string;
  orange: string; // usado por el tipo "security"
}

export const PALETTES: Record<ResolvedTheme, Palette> = {
  dark: {
    bg: "#0D1117",
    surface: "#161B22",
    surface2: "#1C2129",
    border: "#2A313C",
    borderStrong: "#3A424E",
    ink: "#E6EDF3",
    muted: "#8B949E",
    faint: "#6E7681",
    accent: "#8B5CF6",
    accentHover: "#7C3AED",
    high: "#F43F81",
    medium: "#F59E0B",
    low: "#6385FF",
    success: "#2DBF89",
    orange: "#FB7185",
  },
  light: {
    bg: "#F7F9FB",
    surface: "#FFFFFF",
    surface2: "#F1F4F8",
    border: "#DFE3E9",
    borderStrong: "#C8CED6",
    ink: "#181F2A",
    muted: "#5A6472",
    faint: "#828B97",
    accent: "#7C3AED",
    accentHover: "#6D28D9",
    high: "#DB2777",
    medium: "#B46C08",
    low: "#4338CA",
    success: "#0F946A",
    orange: "#E11D6E",
  },
};

/** Convierte un hex (#rrggbb) a rgba con la opacidad dada. */
export function alpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

export function severityColor(p: Palette, s: Severity): string {
  return { high: p.high, medium: p.medium, low: p.low }[s];
}

export function statusColor(p: Palette, s: AgentStatus): string {
  return { ok: p.success, failed: p.high, skipped: p.faint, pending: p.faint }[s];
}

export function typeColor(p: Palette, t: FindingType): string {
  return {
    logic_bug: p.high,
    security: p.orange,
    inconsistency: p.low,
    convention_violation: p.accent,
  }[t];
}

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

export const STATUS_LABEL: Record<AgentStatus, string> = {
  ok: "OK",
  failed: "Falló",
  skipped: "Omitido",
  pending: "Pendiente",
};

export const TYPE_LABEL: Record<FindingType, string> = {
  logic_bug: "Bug lógico",
  security: "Seguridad",
  inconsistency: "Inconsistencia",
  convention_violation: "Convención",
};

/** Escala de series para gráficas multi-serie (por tema). */
export function seriesColors(p: Palette): string[] {
  return [p.accent, p.low, p.medium, p.high, p.orange];
}

import type { NodeKind, LinkType } from "./types";

export function nodeKindColor(p: Palette, kind: NodeKind): string {
  return {
    module: p.accent,
    class: p.low,
    function: p.success,
    method: p.medium,
  }[kind];
}

export const NODE_KIND_LABEL: Record<NodeKind, string> = {
  module: "Módulo",
  class: "Clase",
  function: "Función",
  method: "Método",
};

export const LINK_TYPE_LABEL: Record<LinkType, string> = {
  imports: "importa",
  calls: "llama",
  inherits: "hereda",
  defines: "define",
};
