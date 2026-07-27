import { memo, useMemo } from "react";
import { format } from "date-fns";
import { GitPullRequest, RefreshCw } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/Badge";
import { useStore } from "@/state/StoreProvider";
import type { AgentStatus, ReviewRun } from "@/lib/types";

/**
 * Pantalla de actividad: feed de revisiones reales procesadas por el pipeline.
 *
 * El dashboard es de solo lectura (ver design.md): las revisiones las dispara
 * GitHub vía webhook, nunca el navegador. Esta pantalla refleja lo que el
 * pipeline de Step Functions ya escribió en DynamoDB.
 */
export function ActivityPage() {
  const { runs, selectedRepo, refresh } = useStore();

  // Se recalcula solo cuando cambia el historial de corridas.
  const recent = useMemo(() => [...runs].reverse().slice(0, 30), [runs]);

  return (
    <>
      <Header
        repo={selectedRepo}
        title="Actividad"
        subtitle="Revisiones procesadas por el pipeline de agentes en AWS Step Functions"
      />

      <div className="mb-4 flex justify-end">
        <button onClick={refresh} className="btn-ghost">
          <RefreshCw size={14} />
          Actualizar
        </button>
      </div>

      <Panel title="Actividad reciente" subtitle="Últimas revisiones en todos los repos">
        {recent.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">
            Aún no hay revisiones registradas para este repositorio.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {recent.map((r) => (
              <ActivityRow key={r.pipeline_run_id} run={r} />
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

/** Fila del feed de actividad, memoizada. */
const ActivityRow = memo(function ActivityRow({ run: r }: { run: ReviewRun }) {
  const failed = Object.values(r.agent_status).filter((s) => s === "failed").length;
  const status: AgentStatus = failed > 0 ? "failed" : "ok";
  return (
    <div className="flex items-center gap-3 py-2.5">
      <GitPullRequest size={15} className="shrink-0 text-accent" />
      <span className="font-semibold text-ink">#{r.pr_number}</span>
      <span className="min-w-0 flex-1 truncate text-sm text-muted">{r.pr_title}</span>
      <span className="hidden text-xs text-faint sm:block">{r.repo_full_name.split("/")[1]}</span>
      <span className="text-xs text-faint">{r.findings_summary.total} hallazgos</span>
      <span className="hidden text-xs text-faint md:block">
        {format(new Date(r.created_at), "d MMM HH:mm")}
      </span>
      <StatusBadge status={status} />
    </div>
  );
});
