/**
 * Tipos del dominio de Arcus.
 *
 * Reflejan el esquema definido en:
 *  - .kiro/steering/agent-contracts.md  (Finding)
 *  - .kiro/specs/pr-review-pipeline/design.md  (ítem review_run de DynamoDB)
 *
 * Cuando exista la API real, estos mismos tipos describen la respuesta, así
 * que ni los componentes ni las gráficas cambian.
 */

export type Severity = "high" | "medium" | "low";

export type FindingType =
  | "logic_bug"
  | "security"
  | "inconsistency"
  | "convention_violation";

export type AgentStatus = "ok" | "failed" | "skipped" | "pending";

export type AgentName = "context" | "consistency" | "bugs" | "fixes" | "report";

export interface Fix {
  description: string;
  suggested_diff: string;
  confidence: "high" | "medium" | "low";
}

export interface Finding {
  id: string;
  agent: string;
  type: FindingType;
  severity: Severity;
  file: string;
  line_start: number;
  line_end: number;
  title: string;
  rationale: string;
  evidence_refs: string[];
  fix: Fix | null;
}

export interface FindingsSummary {
  total: number;
  by_severity: Record<Severity, number>;
  by_type: Partial<Record<FindingType, number>>;
}

/** Espejo del ítem `review_run` de DynamoDB (design.md). */
export interface ReviewRun {
  pipeline_run_id: string;
  repo_full_name: string;
  pr_number: number;
  pr_title: string;
  author: string;
  commit_sha: string;
  created_at: string; // ISO-8601
  agent_status: Record<AgentName, AgentStatus>;
  findings_summary: FindingsSummary;
  comment_url: string;
  ran_diff_only: boolean;
  duration_s: number;
}
