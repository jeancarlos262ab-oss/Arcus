/**
 * Selectores / agregaciones puras sobre `ReviewRun[]`.
 *
 * Son funciones sin estado ni dependencias de React: reciben datos del store y
 * devuelven lo que las gráficas y tarjetas necesitan. Fáciles de testear.
 */

import type { Finding, FindingType, ReviewRun, Severity } from "./types";
import type { RangeKey } from "@/state/StoreProvider";

export interface Range {
  start: Date;
  end: Date;
}

export interface OverviewMetrics {
  totalReviews: number;
  totalFindings: number;
  avgFindingsPerPr: number;
  highSeverity: number;
  fixCoverage: number;
  /** null cuando no hay corridas en el rango: no hay pipeline que medir. */
  pipelineReliability: number | null;
  avgDurationS: number;
  deltaReviews: number;
  deltaFindings: number;
  /** null cuando no hay corridas en el rango: no confundir "sin datos" con "perfecto". */
  healthScore: number | null;
}

export interface TimePoint {
  date: string;
  label: string;
  high: number;
  medium: number;
  low: number;
  reviews: number;
}

const RANGE_DAYS: Record<RangeKey, number> = { "30d": 30, "60d": 60, "90d": 90 };

/** Calcula el rango actual y el periodo previo de igual longitud. */
export function rangeFromKey(key: RangeKey): { range: Range; prevRange: Range } {
  const end = new Date();
  const days = RANGE_DAYS[key];
  const start = new Date(end.getTime() - days * 86400000);
  const prevEnd = new Date(start.getTime() - 1);
  const prevStart = new Date(prevEnd.getTime() - days * 86400000);
  return { range: { start, end }, prevRange: { start: prevStart, end: prevEnd } };
}

/** Filtra corridas por repo y rango [start, end]. */
export function filterRuns(runs: ReviewRun[], repo: string, range: Range): ReviewRun[] {
  return runs
    .filter((r) => r.repo_full_name === repo)
    .filter((r) => {
      const t = new Date(r.created_at).getTime();
      return t >= range.start.getTime() && t <= range.end.getTime();
    })
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/** Cobertura de fixes (% de findings con fix) sobre las corridas dadas. */
export function computeFixCoverage(
  getFindings: (runId: string) => Finding[],
  runs: ReviewRun[],
): number {
  let total = 0;
  let withFix = 0;
  for (const r of runs) {
    const f = getFindings(r.pipeline_run_id);
    total += f.length;
    withFix += f.filter((x) => x.fix).length;
  }
  return total > 0 ? (withFix / total) * 100 : 0;
}

/** Métricas de resumen para un conjunto de corridas (+ periodo previo para deltas). */
export function computeOverview(
  runs: ReviewRun[],
  prevRuns: ReviewRun[],
  fixCoveragePct: number,
): OverviewMetrics {
  const totalReviews = runs.length;
  const totalFindings = runs.reduce((s, r) => s + r.findings_summary.total, 0);
  const highSeverity = runs.reduce((s, r) => s + r.findings_summary.by_severity.high, 0);
  const reliableRuns = runs.filter((r) =>
    Object.values(r.agent_status).every((v) => v !== "failed"),
  ).length;
  const avgDurationS =
    totalReviews > 0 ? runs.reduce((s, r) => s + r.duration_s, 0) / totalReviews : 0;

  const prevFindings = prevRuns.reduce((s, r) => s + r.findings_summary.total, 0);

  if (totalReviews === 0) {
    return {
      totalReviews: 0,
      totalFindings: 0,
      avgFindingsPerPr: 0,
      highSeverity: 0,
      fixCoverage: Math.round(fixCoveragePct),
      pipelineReliability: null,
      avgDurationS: 0,
      deltaReviews: -prevRuns.length,
      deltaFindings: -prevFindings,
      healthScore: null,
    };
  }

  const avgFindingsPerPr = totalFindings / totalReviews;
  const pipelineReliability = (reliableRuns / totalReviews) * 100;

  const densityPenalty = Math.min(avgFindingsPerPr * 6, 55);
  const highPenalty = Math.min((highSeverity / totalReviews) * 14, 25);
  const reliabilityBonus = (pipelineReliability / 100) * 12;
  const healthScore = Math.round(
    Math.max(0, Math.min(100, 88 - densityPenalty - highPenalty + reliabilityBonus)),
  );

  return {
    totalReviews,
    totalFindings,
    avgFindingsPerPr: Math.round(avgFindingsPerPr * 10) / 10,
    highSeverity,
    fixCoverage: Math.round(fixCoveragePct),
    pipelineReliability: Math.round(pipelineReliability),
    avgDurationS: Math.round(avgDurationS),
    deltaReviews: totalReviews - prevRuns.length,
    deltaFindings: totalFindings - prevFindings,
    healthScore,
  };
}

/** Agrupa hallazgos por día para la serie temporal. */
export function toTimeSeries(runs: ReviewRun[]): TimePoint[] {
  const byDay = new Map<string, TimePoint>();
  for (const r of runs) {
    const day = r.created_at.slice(0, 10);
    const p = byDay.get(day) ?? {
      date: day,
      label: new Date(r.created_at).toLocaleDateString("es", { day: "numeric", month: "short" }),
      high: 0,
      medium: 0,
      low: 0,
      reviews: 0,
    };
    p.high += r.findings_summary.by_severity.high;
    p.medium += r.findings_summary.by_severity.medium;
    p.low += r.findings_summary.by_severity.low;
    p.reviews += 1;
    byDay.set(day, p);
  }
  return [...byDay.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** Totales por severidad. */
export function severityTotals(runs: ReviewRun[]): Record<Severity, number> {
  return runs.reduce(
    (acc, r) => {
      acc.high += r.findings_summary.by_severity.high;
      acc.medium += r.findings_summary.by_severity.medium;
      acc.low += r.findings_summary.by_severity.low;
      return acc;
    },
    { high: 0, medium: 0, low: 0 } as Record<Severity, number>,
  );
}

/** Totales por tipo de hallazgo. */
export function typeTotals(runs: ReviewRun[]): Record<FindingType, number> {
  const acc: Record<FindingType, number> = {
    logic_bug: 0,
    security: 0,
    inconsistency: 0,
    convention_violation: 0,
  };
  for (const r of runs) {
    for (const [t, c] of Object.entries(r.findings_summary.by_type)) {
      acc[t as FindingType] += c ?? 0;
    }
  }
  return acc;
}

export interface RepoHealthSummary {
  repo: string;
  /** null cuando el repo no tiene ninguna revisión real todavía (no confundir con 100). */
  healthScore: number | null;
  totalFindings: number;
  bySeverity: Record<Severity, number>;
  hasData: boolean;
}

/**
 * Salud resumida por repo (últimos 30 días), para previsualizaciones donde no
 * hay espacio para el detalle completo de `computeOverview` (p. ej. el
 * selector de repos del sidebar). `healthScore` es `null` sin datos: un repo
 * recién conectado no es "perfecto", simplemente no tiene revisiones aún.
 */
export function repoHealthSummaries(runs: ReviewRun[], repos: string[]): RepoHealthSummary[] {
  const { range } = rangeFromKey("30d");
  return repos.map((repo) => {
    const scoped = filterRuns(runs, repo, range);
    const bySeverity = severityTotals(scoped);
    const totalFindings = bySeverity.high + bySeverity.medium + bySeverity.low;
    const hasData = scoped.length > 0;
    if (!hasData) {
      return { repo, healthScore: null, totalFindings, bySeverity, hasData };
    }
    const avgFindingsPerPr = totalFindings / scoped.length;
    const densityPenalty = Math.min(avgFindingsPerPr * 6, 55);
    const highPenalty = Math.min((bySeverity.high / scoped.length) * 14, 25);
    const healthScore = Math.round(Math.max(0, Math.min(100, 88 - densityPenalty - highPenalty)));
    return { repo, healthScore, totalFindings, bySeverity, hasData };
  });
}

/**
 * Fiabilidad por agente: % de corridas donde cada agente terminó en ok.
 * `ok` es null sin corridas: no hay pipeline que medir, no es "100% fiable".
 */
export function agentReliability(
  runs: ReviewRun[],
): { agent: string; ok: number | null }[] {
  const agents = ["context", "consistency", "bugs", "fixes", "report"] as const;
  const labels: Record<string, string> = {
    context: "Context Builder",
    consistency: "Consistency",
    bugs: "Bug Hunter",
    fixes: "Fix Suggester",
    report: "Reporter",
  };
  return agents.map((a) => {
    if (runs.length === 0) return { agent: labels[a], ok: null };
    const okCount = runs.filter((r) => r.agent_status[a] === "ok").length;
    return { agent: labels[a], ok: Math.round((okCount / runs.length) * 100) };
  });
}
