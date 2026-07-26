import { memo } from "react";
import { Lightbulb, ShieldAlert } from "lucide-react";
import type { Finding } from "@/lib/types";
import { typeColor, TYPE_LABEL } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import { SeverityBadge, Chip } from "./Badge";

interface FindingCardProps {
  finding: Finding;
  /** Referencia opcional al PR (para la vista agregada de hallazgos). */
  prRef?: string;
}

/**
 * Tarjeta de un hallazgo con su fix sugerido (diff coloreado).
 *
 * Memoizada: en la vista de Hallazgos se renderizan potencialmente decenas de
 * tarjetas y solo deben re-renderizar cuando su propio `finding` cambia, no
 * cuando cambian los filtros de las demás.
 */
function FindingCardBase({ finding, prRef }: FindingCardProps) {
  const { p } = useTheme();
  return (
    <article className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <ShieldAlert size={16} className="mt-0.5 shrink-0 text-muted" />
          <div>
            <h4 className="text-sm font-bold leading-snug text-ink">{finding.title}</h4>
            <div className="mt-0.5 font-mono text-xs text-faint">
              {finding.file}:{finding.line_start}
              {finding.line_end !== finding.line_start ? `-${finding.line_end}` : ""}
              {prRef && <span className="ml-2 text-accent">{prRef}</span>}
            </div>
          </div>
        </div>
        <SeverityBadge severity={finding.severity} />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Chip color={typeColor(p, finding.type)}>{TYPE_LABEL[finding.type]}</Chip>
        <span className="text-[0.68rem] text-faint">por {finding.agent}</span>
      </div>

      <p className="mt-2.5 text-[0.86rem] leading-relaxed text-muted">{finding.rationale}</p>

      {finding.evidence_refs.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[0.72rem] text-faint">
          <span className="font-semibold uppercase tracking-wide">Evidencia:</span>
          {finding.evidence_refs.map((ref) => (
            <span key={ref} className="font-mono">
              {ref}
            </span>
          ))}
        </div>
      )}

      {finding.fix && (
        <div className="mt-3 rounded-lg border border-border border-l-2 border-l-success bg-bg p-3">
          <div className="flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-success">
            <Lightbulb size={13} />
            Fix sugerido · confianza {finding.fix.confidence}
          </div>
          <p className="mt-1.5 text-[0.84rem] text-ink">{finding.fix.description}</p>
          <pre className="mt-2 overflow-x-auto rounded-md bg-surface-2 p-2.5 font-mono text-[0.76rem] leading-relaxed">
            {finding.fix.suggested_diff.split("\n").map((line, i) => (
              <div
                key={i}
                className={
                  line.startsWith("+")
                    ? "text-success"
                    : line.startsWith("-")
                      ? "text-high"
                      : "text-muted"
                }
              >
                {line}
              </div>
            ))}
          </pre>
        </div>
      )}
    </article>
  );
}

export const FindingCard = memo(FindingCardBase);
