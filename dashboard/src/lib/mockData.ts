/**
 * Generador de datos simulados para el dashboard.
 *
 * Produce `ReviewRun[]` + findings por corrida con el MISMO shape que devolverá
 * la API real (esquema DynamoDB en design.md). Determinista (semilla fija) para
 * que la demo sea estable entre recargas.
 */

import type {
  AgentName,
  AgentStatus,
  Finding,
  FindingType,
  ReviewRun,
  Severity,
} from "./types";

export const REPOS = [
  "arcus-labs/payments-api",
  "arcus-labs/auth-service",
  "arcus-labs/web-frontend",
  "arcus-labs/data-pipeline",
] as const;

const AGENTS: AgentName[] = ["context", "consistency", "bugs", "fixes", "report"];
const FINDING_TYPES: FindingType[] = [
  "logic_bug",
  "security",
  "inconsistency",
  "convention_violation",
];
const SEVERITIES: Severity[] = ["high", "medium", "low"];

const TITLES: Record<FindingType, string[]> = {
  logic_bug: [
    "Posible None dereference en parse_config",
    "Índice fuera de rango en batch_split con lista vacía",
    "Condición de carrera al actualizar el cache compartido",
    "Retorno temprano omite el cierre de la conexión",
    "Comparación con == en vez de is para None",
  ],
  security: [
    "Query SQL por concatenación (riesgo de inyección)",
    "Secreto potencial hardcodeado en el cliente HTTP",
    "Falta validación de firma en el webhook entrante",
    "Uso de eval() sobre entrada no confiable",
    "Token de sesión sin expiración",
  ],
  inconsistency: [
    "El módulo no usa el logger estructurado del repo",
    "El endpoint no sigue el patrón de paginación establecido",
    "DTO definido como dict en vez de modelo Pydantic",
    "Manejo de error ad-hoc en vez de las excepciones custom",
  ],
  convention_violation: [
    "Nombres en camelCase; el repo usa snake_case",
    "Función pública sin type hints",
    "Falta docstring en clase pública",
    "Import relativo donde el repo usa imports absolutos",
  ],
};

const RATIONALES = [
  "El resto del repo valida esta ruta antes de usarla; aquí se omite.",
  "Este patrón aparece en 7 módulos del repo; el PR se desvía de él.",
  "El grafo de contexto muestra que este símbolo se consume en 3 lugares.",
  "La convención dominante detectada en el repo contradice este cambio.",
  "El vecino directo en el grafo asume un contrato que este cambio rompe.",
];

const FIX_DESCRIPTIONS = [
  "Validar la entrada con la función existente antes de acceder al atributo.",
  "Reemplazar la concatenación por una consulta parametrizada.",
  "Usar el logger estructurado de arcus.logging en vez de print.",
  "Definir el DTO como modelo Pydantic en contracts/.",
  "Agregar type hints completos y docstring estilo Google.",
];

const FILES = ["src/service.py", "src/handlers.py", "src/models.py", "src/utils.py", "src/api.py"];
const AUTHORS = ["mgomez", "lchen", "aptorres", "rkumar", "dsilva"];
const PR_VERBS = ["Add", "Refactor", "Fix", "Improve", "Remove", "Optimize", "Update"];
const PR_OBJECTS = [
  "retry logic in Bedrock client",
  "pagination on /users endpoint",
  "webhook signature validation",
  "graph serialization to S3",
  "DynamoDB idempotent writes",
  "config loading path",
  "error handling in reporter",
  "token refresh flow",
];

/** PRNG determinista (mulberry32). */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rand: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rand() * arr.length)];
}

function randInt(rand: () => number, min: number, max: number): number {
  return Math.floor(rand() * (max - min + 1)) + min;
}

/** Aproximación gaussiana (Box-Muller) para conteos con dispersión natural. */
function gauss(rand: () => number, mean: number, std: number): number {
  const u = Math.max(rand(), 1e-9);
  const v = rand();
  const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  return mean + z * std;
}

function shortHash(input: string): string {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).padStart(7, "0").slice(0, 7);
}

function makeFindings(
  rand: () => number,
  runId: string,
  countsByType: Record<FindingType, number>,
): Finding[] {
  const findings: Finding[] = [];
  (Object.keys(countsByType) as FindingType[]).forEach((ftype) => {
    for (let i = 0; i < countsByType[ftype]; i++) {
      const severity = pick(rand, SEVERITIES);
      const lineStart = randInt(rand, 10, 480);
      const hasFix = rand() > 0.15;
      const agent =
        ftype === "logic_bug" || ftype === "security" ? "bug_hunter" : "consistency_checker";
      findings.push({
        id: shortHash(`${runId}-${ftype}-${lineStart}-${i}`),
        agent,
        type: ftype,
        severity,
        file: pick(rand, FILES),
        line_start: lineStart,
        line_end: lineStart + randInt(rand, 0, 12),
        title: pick(rand, TITLES[ftype]),
        rationale: pick(rand, RATIONALES),
        evidence_refs: Array.from({ length: randInt(rand, 1, 2) }, () => {
          const f = pick(rand, ["src/config.py", "src/loader.py", "src/base.py"]);
          return `${f}:${randInt(rand, 5, 90)}`;
        }),
        fix: hasFix
          ? {
              description: pick(rand, FIX_DESCRIPTIONS),
              suggested_diff: `@@ -${lineStart},3 +${lineStart},4 @@\n-    return cfg.timeout\n+    validate_config(cfg)\n+    return cfg.timeout`,
              confidence: pick(rand, ["high", "medium", "low"] as const),
            }
          : null,
      });
    }
  });
  return findings;
}

export interface Dataset {
  runs: ReviewRun[];
  findingsByRun: Record<string, Finding[]>;
}

/** Genera el dataset simulado completo (determinista). */
export function generateDataset(): Dataset {
  const rand = mulberry32(20260721);
  const now = Date.now();
  const runs: ReviewRun[] = [];
  const findingsByRun: Record<string, Finding[]> = {};

  for (const repo of REPOS) {
    const quality = 0.4 + rand() * 0.5; // salud del repo
    const nRuns = randInt(rand, 18, 34);
    let prNumber = randInt(rand, 40, 120);

    for (let i = 0; i < nRuns; i++) {
      const daysAgo = rand() * 88;
      const created = new Date(now - daysAgo * 86400000 - rand() * 82800000);
      prNumber += randInt(rand, 1, 4);
      const runId = shortHash(`${repo}-${prNumber}-${daysAgo}`);
      const commitSha = shortHash(`${repo}-${runId}-commit`);

      const ranDiffOnly = rand() > 0.92;
      const agentStatus = {} as Record<AgentName, AgentStatus>;
      for (const agent of AGENTS) {
        if (agent === "context" && ranDiffOnly) agentStatus[agent] = "failed";
        else agentStatus[agent] = rand() > 0.04 + (1 - quality) * 0.06 ? "ok" : "failed";
      }
      agentStatus.report = "ok"; // el Reporter siempre corre (design.md)

      const total = Math.max(0, Math.round(gauss(rand, (1 - quality) * 9, 2.2)));
      const countsByType = {
        logic_bug: 0,
        security: 0,
        inconsistency: 0,
        convention_violation: 0,
      } as Record<FindingType, number>;
      for (let k = 0; k < total; k++) {
        countsByType[pick(rand, FINDING_TYPES)] += 1;
      }

      const runFindings = makeFindings(rand, runId, countsByType);
      const bySeverity: Record<Severity, number> = { high: 0, medium: 0, low: 0 };
      for (const f of runFindings) bySeverity[f.severity] += 1;
      const byType: Partial<Record<FindingType, number>> = {};
      (Object.keys(countsByType) as FindingType[]).forEach((t) => {
        if (countsByType[t] > 0) byType[t] = countsByType[t];
      });

      runs.push({
        pipeline_run_id: runId,
        repo_full_name: repo,
        pr_number: prNumber,
        pr_title: `${pick(rand, PR_VERBS)} ${pick(rand, PR_OBJECTS)}`,
        author: pick(rand, AUTHORS),
        commit_sha: commitSha,
        created_at: created.toISOString(),
        agent_status: agentStatus,
        findings_summary: { total: runFindings.length, by_severity: bySeverity, by_type: byType },
        comment_url: `https://github.com/${repo}/pull/${prNumber}`,
        ran_diff_only: ranDiffOnly,
        duration_s: Math.round((22 + rand() * 73) * 10) / 10,
      });
      findingsByRun[runId] = runFindings;
    }
  }

  runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return { runs, findingsByRun };
}
