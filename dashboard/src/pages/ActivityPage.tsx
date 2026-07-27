<<<<<<< HEAD
import { memo, useMemo, useRef, useState } from "react";
=======
import { memo, useMemo } from "react";
>>>>>>> 09fe95a (dashboard)
import { format } from "date-fns";
import { GitPullRequest, RefreshCw } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/Badge";
import { useStore } from "@/state/StoreProvider";
<<<<<<< HEAD
import type { LogLine } from "@/lib/simulate";
=======
>>>>>>> 09fe95a (dashboard)
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

<<<<<<< HEAD
  const [repo, setRepo] = useState(selectedRepo);
  const [prNumber, setPrNumber] = useState("128");
  const [prTitle, setPrTitle] = useState("Refactor retry logic in Bedrock client");
  const [author, setAuthor] = useState("mgomez");

  const [lines, setLines] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const start = async () => {
    if (running) return;
    const n = parseInt(prNumber, 10);
    if (!Number.isFinite(n) || n <= 0) return;

    setLines([]);
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await runReview(
        { repo, prNumber: n, prTitle: prTitle.trim() || `PR #${n}`, author: author.trim() || "anon" },
        (line) => setLines((prev) => [...prev, line]),
        ctrl.signal,
      );
    } catch {
      // Cancelado por el usuario: no hacemos nada más.
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const cancel = () => abortRef.current?.abort();

  // Se recalcula solo cuando cambia el historial de corridas, no en cada
  // línea de log que llega mientras el pipeline está "corriendo".
  const recent = useMemo(() => [...runs].reverse().slice(0, 15), [runs]);
  const repoOptions = useMemo(() => repos.map((r) => ({ value: r, label: r })), [repos]);
=======
  // Se recalcula solo cuando cambia el historial de corridas.
  const recent = useMemo(() => [...runs].reverse().slice(0, 30), [runs]);
>>>>>>> 09fe95a (dashboard)

  return (
    <>
      <Header
        repo={selectedRepo}
        title="Actividad"
        subtitle="Revisiones procesadas por el pipeline de agentes en AWS Step Functions"
      />

<<<<<<< HEAD
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5 lg:items-stretch">
        {/* Formulario */}
        <div className="lg:col-span-2">
          <Panel title="Nueva revisión" subtitle="Simula la apertura de un PR" className="h-full">
            <div className="space-y-3.5">
              <Field label="Repositorio">
                <Select value={repo} onChange={setRepo} options={repoOptions} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Número de PR">
                  <input
                    className="input"
                    value={prNumber}
                    inputMode="numeric"
                    onChange={(e) => setPrNumber(e.target.value.replace(/[^\d]/g, ""))}
                  />
                </Field>
                <Field label="Autor">
                  <input className="input" value={author} onChange={(e) => setAuthor(e.target.value)} />
                </Field>
              </div>
              <Field label="Título del PR">
                <input className="input" value={prTitle} onChange={(e) => setPrTitle(e.target.value)} />
              </Field>

              <div className="flex gap-2 pt-1">
                <button onClick={start} disabled={running} className="btn-primary flex-1">
                  <Play size={16} />
                  {running ? "Ejecutando…" : "Ejecutar revisión"}
                </button>
                {running && (
                  <button onClick={cancel} className="btn-ghost">
                    <Ban size={16} />
                    Cancelar
                  </button>
                )}
              </div>
              <p className="text-[0.72rem] text-faint">
                La revisión ejecuta los 5 agentes y agrega el resultado al historial (se refleja
                en Resumen y Hallazgos).
              </p>
            </div>
          </Panel>
        </div>

        {/* Terminal */}
        <div className="lg:col-span-3">
          <Terminal lines={lines} running={running} className="h-full" />
        </div>
      </div>

      {/* Feed de actividad */}
      <div className="mt-4">
        <Panel title="Actividad reciente" subtitle="Últimas revisiones en todos los repos">
          {recent.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">Aún no hay revisiones.</p>
          ) : (
            <div className="divide-y divide-border">
              {recent.map((r) => (
                <ActivityRow key={r.pipeline_run_id} run={r} />
              ))}
            </div>
          )}
        </Panel>
      </div>
=======
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
>>>>>>> 09fe95a (dashboard)
    </>
  );
}

<<<<<<< HEAD
/** Fila del feed de actividad, memoizada para no re-renderizar mientras el terminal transmite logs. */
=======
/** Fila del feed de actividad, memoizada. */
>>>>>>> 09fe95a (dashboard)
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
