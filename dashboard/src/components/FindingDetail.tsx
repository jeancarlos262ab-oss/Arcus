import { Check, FileCode2 } from "lucide-react";
import type { Finding, ReviewRun } from "@/lib/types";
import { StatusBadge } from "./Badge";
import { FindingCard } from "./FindingCard";

interface FindingDetailProps {
  run: ReviewRun | null;
  findings: Finding[];
}

/** Panel de detalle de una revisión: estado de agentes + lista de hallazgos. */
export function FindingDetail({ run, findings }: FindingDetailProps) {
  if (!run) {
    return (
      <div className="flex h-full flex-col items-center justify-center py-16 text-center">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-faint">
          <FileCode2 size={22} />
        </div>
        <p className="mt-3 text-sm font-medium text-muted">Selecciona una revisión</p>
        <p className="mt-1 text-xs text-faint">
          Elige un PR de la tabla para ver sus hallazgos y fixes sugeridos.
        </p>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold text-ink">PR #{run.pr_number}</h3>
          <span className="font-mono text-xs text-faint">{run.commit_sha}</span>
        </div>
        <p className="mt-0.5 text-sm text-muted">{run.pr_title}</p>
      </div>

      <div>
        <div className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wider text-faint">
          Pipeline de agentes
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(run.agent_status).map(([agent, status]) => (
            <div
              key={agent}
              className="flex items-center gap-1.5 rounded-lg bg-surface-2 px-2.5 py-1.5"
            >
              <span className="text-xs capitalize text-muted">{agent}</span>
              <StatusBadge status={status} />
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wider text-faint">
          {findings.length} hallazgo{findings.length === 1 ? "" : "s"}
        </div>
        {findings.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2.5 text-sm text-success">
            <Check size={16} />
            No se detectaron problemas en este PR.
          </div>
        ) : (
          <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
            {findings.map((f) => (
              <FindingCard key={f.id} finding={f} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
