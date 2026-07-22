import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { FindingCard } from "@/components/FindingCard";
import { useStore } from "@/state/StoreProvider";
import { filterRuns, rangeFromKey } from "@/lib/selectors";
import { SEVERITY_LABEL, TYPE_LABEL } from "@/lib/theme";
import type { Finding, FindingType, Severity } from "@/lib/types";

type SevFilter = Severity | "all";
type TypeFilter = FindingType | "all";

interface EnrichedFinding extends Finding {
  prNumber: number;
}

/** Pantalla de hallazgos: vista agregada con filtros por severidad, tipo y texto. */
export function FindingsPage() {
  const { runs, selectedRepo, rangeKey, getFindings } = useStore();
  const [sev, setSev] = useState<SevFilter>("all");
  const [type, setType] = useState<TypeFilter>("all");
  const [query, setQuery] = useState("");

  const { range } = useMemo(() => rangeFromKey(rangeKey), [rangeKey]);

  const all = useMemo<EnrichedFinding[]>(() => {
    const scoped = filterRuns(runs, selectedRepo, range);
    const out: EnrichedFinding[] = [];
    for (const r of scoped) {
      for (const f of getFindings(r.pipeline_run_id)) {
        out.push({ ...f, prNumber: r.pr_number });
      }
    }
    const order: Record<Severity, number> = { high: 0, medium: 1, low: 2 };
    return out.sort((a, b) => order[a.severity] - order[b.severity]);
  }, [runs, selectedRepo, range, getFindings]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return all.filter((f) => {
      if (sev !== "all" && f.severity !== sev) return false;
      if (type !== "all" && f.type !== type) return false;
      if (q && !(`${f.title} ${f.rationale} ${f.file}`.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [all, sev, type, query]);

  const counts = useMemo(() => {
    const c = { high: 0, medium: 0, low: 0 };
    for (const f of all) c[f.severity] += 1;
    return c;
  }, [all]);

  const sevOptions: { value: SevFilter; label: string }[] = [
    { value: "all", label: `Todas (${all.length})` },
    { value: "high", label: `${SEVERITY_LABEL.high} (${counts.high})` },
    { value: "medium", label: `${SEVERITY_LABEL.medium} (${counts.medium})` },
    { value: "low", label: `${SEVERITY_LABEL.low} (${counts.low})` },
  ];
  const typeOptions: { value: TypeFilter; label: string }[] = [
    { value: "all", label: "Todos los tipos" },
    ...(Object.keys(TYPE_LABEL) as FindingType[]).map((t) => ({ value: t, label: TYPE_LABEL[t] })),
  ];

  return (
    <>
      <Header
        repo={selectedRepo}
        title="Hallazgos"
        subtitle={`Todos los hallazgos de ${selectedRepo.split("/")[1]} en el rango seleccionado`}
      />

      <Panel className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              className="input pl-9"
              placeholder="Buscar por título, archivo o razón…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <FilterPills value={sev} onChange={setSev} options={sevOptions} />
          <FilterPills value={type} onChange={setType} options={typeOptions} />
        </div>
      </Panel>

      {filtered.length === 0 ? (
        <Panel>
          <p className="py-10 text-center text-sm text-muted">
            No hay hallazgos que coincidan con los filtros.
          </p>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map((f) => (
            <FindingCard key={`${f.id}-${f.prNumber}`} finding={f} prRef={`#${f.prNumber}`} />
          ))}
        </div>
      )}
    </>
  );
}

function FilterPills<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`focus-ring rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
            value === o.value
              ? "border-accent bg-accent/10 text-accent"
              : "border-border bg-surface text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
