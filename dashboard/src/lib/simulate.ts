/**
 * Simulación del pipeline de agentes en vivo.
 *
 * `simulateReview` reproduce la ejecución del pipeline (Context Builder →
 * Consistency → Bug Hunter → Fix Suggester → Reporter) emitiendo líneas de log
 * con retardos, como si corriera de verdad en Step Functions. Al terminar
 * devuelve el `ReviewRun` + sus `Finding[]`, listos para agregarse al store.
 *
 * Cuando exista el backend real, esta simulación se reemplaza por un stream
 * (WebSocket / polling) desde la ejecución de Step Functions.
 */

import type {
  AgentName,
  AgentStatus,
  Finding,
  FindingType,
  ReviewRun,
  Severity,
} from "./types";

export type LogLevel = "info" | "success" | "warn" | "error";

export interface LogLine {
  id: string;
  ts: string; // HH:MM:SS
  agent: string;
  level: LogLevel;
  message: string;
}

export interface NewReviewInput {
  repo: string;
  prNumber: number;
  prTitle: string;
  author: string;
}

const FINDING_TYPES: FindingType[] = [
  "logic_bug",
  "security",
  "inconsistency",
  "convention_violation",
];
const SEVERITIES: Severity[] = ["high", "medium", "low"];
const FILES = ["src/service.py", "src/handlers.py", "src/models.py", "src/utils.py", "src/api.py"];

const TITLES: Record<FindingType, string[]> = {
  logic_bug: [
    "Posible None dereference en parse_config",
    "Índice fuera de rango en batch_split con lista vacía",
    "Retorno temprano omite el cierre de la conexión",
  ],
  security: [
    "Query SQL por concatenación (riesgo de inyección)",
    "Secreto potencial hardcodeado en el cliente HTTP",
    "Falta validación de firma en el webhook entrante",
  ],
  inconsistency: [
    "El módulo no usa el logger estructurado del repo",
    "DTO definido como dict en vez de modelo Pydantic",
  ],
  convention_violation: [
    "Nombres en camelCase; el repo usa snake_case",
    "Función pública sin type hints",
  ],
};

const RATIONALES = [
  "El resto del repo valida esta ruta antes de usarla; aquí se omite.",
  "Este patrón aparece en varios módulos del repo; el PR se desvía de él.",
  "El grafo de contexto muestra que este símbolo se consume en 3 lugares.",
];

const FIXES = [
  "Validar la entrada con la función existente antes de acceder al atributo.",
  "Reemplazar la concatenación por una consulta parametrizada.",
  "Usar el logger estructurado de arcus.logging en vez de print.",
];

const pick = <T>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)];
const randInt = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
const uid = () => Math.random().toString(36).slice(2, 9);
const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function now(): string {
  return new Date().toLocaleTimeString("es", { hour12: false });
}

interface AgentStep {
  key: AgentName;
  label: string;
  lines: string[];
}

const STEPS: AgentStep[] = [
  {
    key: "context",
    label: "Context Builder",
    lines: [
      "Cargando grafo del repo desde S3…",
      "Parseando archivos cambiados con tree-sitter",
      "Extrayendo subgrafo relevante (1 salto)",
    ],
  },
  {
    key: "consistency",
    label: "Consistency Checker",
    lines: ["Comparando el diff contra patrones del repo", "Evaluando convenciones detectadas"],
  },
  {
    key: "bugs",
    label: "Bug Hunter",
    lines: ["Analizando lógica con contexto del grafo", "Buscando vectores de seguridad"],
  },
  {
    key: "fixes",
    label: "Fix Suggester",
    lines: ["Generando fixes para los hallazgos"],
  },
  {
    key: "report",
    label: "Reporter",
    lines: ["Sintetizando comentario Markdown", "Publicando en el PR", "Escribiendo en DynamoDB"],
  },
];

function buildFindings(total: number): Finding[] {
  const findings: Finding[] = [];
  for (let i = 0; i < total; i++) {
    const type = pick(FINDING_TYPES);
    const severity = pick(SEVERITIES);
    const lineStart = randInt(10, 460);
    const hasFix = Math.random() > 0.15;
    const agent = type === "logic_bug" || type === "security" ? "bug_hunter" : "consistency_checker";
    findings.push({
      id: uid(),
      agent,
      type,
      severity,
      file: pick(FILES),
      line_start: lineStart,
      line_end: lineStart + randInt(0, 10),
      title: pick(TITLES[type]),
      rationale: pick(RATIONALES),
      evidence_refs: [`${pick(["src/config.py", "src/base.py"])}:${randInt(5, 90)}`],
      fix: hasFix
        ? {
            description: pick(FIXES),
            suggested_diff: `@@ -${lineStart},3 +${lineStart},4 @@\n-    return cfg.timeout\n+    validate_config(cfg)\n+    return cfg.timeout`,
            confidence: pick(["high", "medium", "low"] as const),
          }
        : null,
    });
  }
  return findings;
}

export interface SimulationResult {
  run: ReviewRun;
  findings: Finding[];
}

/**
 * Ejecuta la simulación del pipeline, emitiendo logs por callback.
 *
 * @param input   Datos del PR a revisar.
 * @param emit    Se llama por cada línea de log producida.
 * @param opts    `signal` para cancelar; `speed` multiplicador de retardo (1 = normal).
 */
export async function simulateReview(
  input: NewReviewInput,
  emit: (line: LogLine) => void,
  opts: { signal?: AbortSignal; speed?: number } = {},
): Promise<SimulationResult> {
  const speed = opts.speed ?? 1;
  const runId = uid();
  const commitSha = uid().slice(0, 7);
  const aborted = () => opts.signal?.aborted;

  const log = (agent: string, level: LogLevel, message: string) =>
    emit({ id: uid(), ts: now(), agent, level, message });

  log("pipeline", "info", `Iniciando revisión de ${input.repo} PR #${input.prNumber}`);
  log("pipeline", "info", `commit ${commitSha} · run ${runId}`);
  await delay(400 * speed);

  const agentStatus: Record<AgentName, AgentStatus> = {
    context: "pending",
    consistency: "pending",
    bugs: "pending",
    fixes: "pending",
    report: "pending",
  };
  let ranDiffOnly = false;

  for (const step of STEPS) {
    if (aborted()) throw new DOMException("Cancelado", "AbortError");
    log(step.label, "info", `▶ ${step.label} iniciado`);
    for (const line of step.lines) {
      if (aborted()) throw new DOMException("Cancelado", "AbortError");
      await delay(randInt(300, 700) * speed);
      log(step.label, "info", line);
    }

    // Context Builder puede degradar a modo diff-only (poco frecuente).
    if (step.key === "context" && Math.random() > 0.85) {
      ranDiffOnly = true;
      agentStatus.context = "failed";
      log(step.label, "warn", "No se pudo cargar el grafo; se continúa en modo diff-only");
    } else {
      agentStatus[step.key] = "ok";
      log(step.label, "success", `✔ ${step.label} completado`);
    }
    await delay(200 * speed);
  }

  const total = randInt(0, 7);
  const findings = buildFindings(total);
  const bySeverity: Record<Severity, number> = { high: 0, medium: 0, low: 0 };
  const byType: Partial<Record<FindingType, number>> = {};
  for (const f of findings) {
    bySeverity[f.severity] += 1;
    byType[f.type] = (byType[f.type] ?? 0) + 1;
  }

  log(
    "Reporter",
    findings.length > 0 ? "warn" : "success",
    findings.length > 0
      ? `${findings.length} hallazgos publicados (${bySeverity.high} alta, ${bySeverity.medium} media)`
      : "No se detectaron problemas. Comentario publicado.",
  );
  log("pipeline", "success", "Pipeline finalizado");

  const run: ReviewRun = {
    pipeline_run_id: runId,
    repo_full_name: input.repo,
    pr_number: input.prNumber,
    pr_title: input.prTitle,
    author: input.author,
    commit_sha: commitSha,
    created_at: new Date().toISOString(),
    agent_status: agentStatus,
    findings_summary: { total: findings.length, by_severity: bySeverity, by_type: byType },
    comment_url: `https://github.com/${input.repo}/pull/${input.prNumber}`,
    ran_diff_only: ranDiffOnly,
    duration_s: randInt(24, 92),
  };

  return { run, findings };
}
