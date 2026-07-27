import { useMemo, useState } from "react";
import { AlertTriangle, GitPullRequest, ShieldCheck, Wrench } from "lucide-react";

import { Header } from "@/components/Header";
import { KpiCard } from "@/components/KpiCard";
import { Panel } from "@/components/Panel";
import { HealthScore } from "@/components/HealthScore";
import { ReviewsTable } from "@/components/ReviewsTable";
import { FindingDetail } from "@/components/FindingDetail";
import { FindingsOverTime } from "@/components/charts/FindingsOverTime";
import { SeverityDonut } from "@/components/charts/SeverityDonut";
import { FindingsByType } from "@/components/charts/FindingsByType";
import { AgentReliability } from "@/components/charts/AgentReliability";

import { useStore } from "@/state/StoreProvider";
import {
  agentReliability,
  computeFixCoverage,
  computeOverview,
  filterRuns,
  rangeFromKey,
  severityTotals,
  toTimeSeries,
  typeTotals,
} from "@/lib/selectors";

/** Pantalla principal: KPIs, tendencias, salud y detalle de revisiones. */
export function OverviewPage() {
  const { runs, selectedRepo, rangeKey, setRangeKey, getFindings } = useStore();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { range, prevRange } = useMemo(() => rangeFromKey(rangeKey), [rangeKey]);
  const scoped = useMemo(
    () => filterRuns(runs, selectedRepo, range),
    [runs, selectedRepo, range],
  );
  const prevScoped = useMemo(
    () => filterRuns(runs, selectedRepo, prevRange),
    [runs, selectedRepo, prevRange],
  );

  const fixCoverage = useMemo(() => computeFixCoverage(getFindings, scoped), [getFindings, scoped]);
  const overview = useMemo(
    () => computeOverview(scoped, prevScoped, fixCoverage),
    [scoped, prevScoped, fixCoverage],
  );
  const timeSeries = useMemo(() => toTimeSeries(scoped), [scoped]);
  const sevTotals = useMemo(() => severityTotals(scoped), [scoped]);
  const typTotals = useMemo(() => typeTotals(scoped), [scoped]);
  const reliability = useMemo(() => agentReliability(scoped), [scoped]);

  const selectedRun = useMemo(
    () => scoped.find((r) => r.pipeline_run_id === selectedRunId) ?? null,
    [scoped, selectedRunId],
  );
  const selectedFindings = selectedRunId ? getFindings(selectedRunId) : [];

  const trend = (d: number): "up" | "down" | "flat" => (d > 0 ? "up" : d < 0 ? "down" : "flat");
  const fmtDelta = (d: number, noun: string) =>
    `${d > 0 ? "+" : ""}${d} ${noun} vs. periodo previo`;

  return (
    <>
      <Header
        repo={selectedRepo}
        title={selectedRepo.split("/")[1] ?? selectedRepo}
        subtitle="Salud del repositorio y hallazgos de revisión a lo largo del tiempo"
        rangeKey={rangeKey}
        onRangeChange={setRangeKey}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="PRs revisados"
          value={String(overview.totalReviews)}
          icon={GitPullRequest}
          delta={fmtDelta(overview.deltaReviews, "PRs")}
          trend={trend(overview.deltaReviews)}
          upIsGood
          accent
        />
        <KpiCard
          label="Hallazgos totales"
          value={String(overview.totalFindings)}
          icon={AlertTriangle}
          delta={fmtDelta(overview.deltaFindings, "hallazgos")}
          trend={trend(overview.deltaFindings)}
          upIsGood={false}
        />
        <KpiCard
          label="Cobertura de fixes"
          value={`${overview.fixCoverage}%`}
          icon={Wrench}
          delta="findings con fix propuesto"
          trend="flat"
        />
        <KpiCard
          label="Fiabilidad pipeline"
          value={`${overview.pipelineReliability}%`}
          icon={ShieldCheck}
          delta={`${overview.avgDurationS}s de duración media`}
          trend="flat"
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Hallazgos en el tiempo" subtitle="Volumen diario por severidad">
            <FindingsOverTime data={timeSeries} />
          </Panel>
        </div>
        <Panel title="Salud del repo" subtitle="Índice compuesto 0–100">
          <div className="flex flex-col items-center gap-4 py-2">
            <HealthScore score={overview.healthScore} />
            <div className="grid w-full grid-cols-2 gap-3">
              <MiniStat label="Alta severidad" value={overview.highSeverity} tone="high" />
              <MiniStat label="Media/PR" value={overview.avgFindingsPerPr} tone="muted" />
            </div>
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Por severidad" subtitle="Distribución en el rango">
          <SeverityDonut totals={sevTotals} />
        </Panel>
        <Panel title="Por tipo de hallazgo" subtitle="Qué encuentra Arcus">
          <FindingsByType totals={typTotals} />
        </Panel>
        <Panel title="Fiabilidad por agente" subtitle="% de corridas en OK">
          <div className="py-2">
            <AgentReliability data={reliability} />
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Revisiones recientes" subtitle="Haz clic en una fila para ver los hallazgos">
            <ReviewsTable runs={scoped} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
          </Panel>
        </div>
        <Panel title="Detalle de la revisión">
          <FindingDetail run={selectedRun} findings={selectedFindings} />
        </Panel>
      </div>
    </>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "high" | "muted";
}) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2.5">
      <div className={`text-xl font-extrabold ${tone === "high" ? "text-high" : "text-ink"}`}>
        {value}
      </div>
      <div className="text-[0.68rem] font-medium text-muted">{label}</div>
    </div>
  );
}
