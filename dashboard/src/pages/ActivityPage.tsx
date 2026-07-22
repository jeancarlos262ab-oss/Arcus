import { useRef, useState } from "react";
import { format } from "date-fns";
import { Ban, GitPullRequest, Play } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { Terminal } from "@/components/Terminal";
import { Field, Select } from "@/components/ui/Field";
import { StatusBadge } from "@/components/Badge";
import { useStore } from "@/state/StoreProvider";
import type { LogLine } from "@/lib/simulate";
import type { AgentStatus } from "@/lib/types";

/** Pantalla de actividad: ejecutar revisiones (con terminal en vivo) + feed. */
export function ActivityPage() {
  const { repos, runs, selectedRepo, runReview } = useStore();

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

  const recent = [...runs].reverse().slice(0, 15);
  const repoOptions = repos.map((r) => ({ value: r, label: r }));

  return (
    <>
      <Header
        repo={selectedRepo}
        title="Actividad"
        subtitle="Dispara una revisión y observa el pipeline de agentes en tiempo real"
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* Formulario */}
        <div className="lg:col-span-2">
          <Panel title="Nueva revisión" subtitle="Simula la apertura de un PR">
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
          <Terminal lines={lines} running={running} />
        </div>
      </div>

      {/* Feed de actividad */}
      <div className="mt-4">
        <Panel title="Actividad reciente" subtitle="Últimas revisiones en todos los repos">
          {recent.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">Aún no hay revisiones.</p>
          ) : (
            <div className="divide-y divide-border">
              {recent.map((r) => {
                const failed = Object.values(r.agent_status).filter((s) => s === "failed").length;
                const status: AgentStatus = failed > 0 ? "failed" : "ok";
                return (
                  <div key={r.pipeline_run_id} className="flex items-center gap-3 py-2.5">
                    <GitPullRequest size={15} className="shrink-0 text-accent" />
                    <span className="font-semibold text-ink">#{r.pr_number}</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-muted">{r.pr_title}</span>
                    <span className="hidden text-xs text-faint sm:block">
                      {r.repo_full_name.split("/")[1]}
                    </span>
                    <span className="text-xs text-faint">{r.findings_summary.total} hallazgos</span>
                    <span className="hidden text-xs text-faint md:block">
                      {format(new Date(r.created_at), "d MMM HH:mm")}
                    </span>
                    <StatusBadge status={status} />
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
