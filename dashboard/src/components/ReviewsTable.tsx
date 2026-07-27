import { memo, useMemo } from "react";
import { format } from "date-fns";
import { ExternalLink, GitPullRequest } from "lucide-react";
import type { ReviewRun, Severity } from "@/lib/types";
import { SeverityBadge } from "./Badge";

interface ReviewsTableProps {
  runs: ReviewRun[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}

/** Tabla de revisiones recientes con drill-down por fila. */
export function ReviewsTable({ runs, selectedRunId, onSelect }: ReviewsTableProps) {
  // Evita reordenar/recortar el arreglo en cada render mientras `runs` no cambie.
  const recent = useMemo(() => [...runs].reverse().slice(0, 12), [runs]);

  if (recent.length === 0) {
    return <p className="py-8 text-center text-sm text-muted">No hay revisiones en este rango.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-[0.7rem] uppercase tracking-wider text-muted">
            <Th>PR</Th>
            <Th>Título</Th>
            <Th>Autor</Th>
            <Th>Fecha</Th>
            <Th className="text-center">Hallazgos</Th>
            <Th className="text-center">Severidad top</Th>
            <Th className="text-right">Pipeline</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {recent.map((r) => (
            <ReviewRow
              key={r.pipeline_run_id}
              run={r}
              active={r.pipeline_run_id === selectedRunId}
              onSelect={onSelect}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ReviewRowProps {
  run: ReviewRun;
  active: boolean;
  onSelect: (runId: string) => void;
}

/** Fila individual, memoizada: solo re-renderiza si su run o su selección cambian. */
const ReviewRow = memo(function ReviewRow({ run: r, active, onSelect }: ReviewRowProps) {
  const failed = Object.values(r.agent_status).filter((s) => s === "failed").length;
  const topSeverity: Severity | null =
    r.findings_summary.by_severity.high > 0
      ? "high"
      : r.findings_summary.by_severity.medium > 0
        ? "medium"
        : r.findings_summary.by_severity.low > 0
          ? "low"
          : null;

  return (
    <tr
      onClick={() => onSelect(r.pipeline_run_id)}
      className={`cursor-pointer border-t border-border transition-colors ${
        active ? "bg-accent-soft" : "hover:bg-surface-2"
      }`}
    >
      <Td>
        <span className="flex items-center gap-1.5 font-bold text-ink">
          <GitPullRequest size={14} className="text-accent" />#{r.pr_number}
        </span>
      </Td>
      <Td className="max-w-[260px]">
        <span className="block truncate text-ink">{r.pr_title}</span>
        {r.ran_diff_only && (
          <span className="text-[0.68rem] text-medium">sin contexto global</span>
        )}
      </Td>
      <Td className="text-muted">{r.author}</Td>
      <Td className="whitespace-nowrap text-muted">{format(new Date(r.created_at), "d MMM")}</Td>
      <Td className="text-center font-semibold text-ink">{r.findings_summary.total}</Td>
      <Td className="text-center">
        {topSeverity ? <SeverityBadge severity={topSeverity} /> : <span className="text-faint">—</span>}
      </Td>
      <Td className="text-right">
        {failed === 0 ? (
          <span className="text-xs font-semibold text-success">OK</span>
        ) : (
          <span className="text-xs font-semibold text-high">{failed} falló</span>
        )}
      </Td>
      <Td className="text-right">
        <a
          href={r.comment_url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex text-faint transition-colors hover:text-accent"
          title="Ver PR en GitHub"
        >
          <ExternalLink size={15} />
        </a>
      </Td>
    </tr>
  );
});

function Th({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-3.5 py-2.5 font-semibold ${className}`}>{children}</th>;
}

function Td({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-3.5 py-3 ${className}`}>{children}</td>;
}
