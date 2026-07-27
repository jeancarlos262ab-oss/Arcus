import { useEffect, useMemo, useState } from "react";
import { Boxes, GitBranch, RefreshCw, TriangleAlert, Workflow } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { GraphView } from "@/components/GraphView";
import { useStore } from "@/state/StoreProvider";
import { useTheme } from "@/state/ThemeProvider";
import { ApiRequestError, fetchGraph } from "@/lib/api";
import { LINK_TYPE_LABEL, NODE_KIND_LABEL, nodeKindColor } from "@/lib/theme";
import type { NodeKind, RepoGraph } from "@/lib/types";

const EMPTY_GRAPH: RepoGraph = {
  repo: "",
  graph_version: "",
  language: "python",
  nodes: [],
  links: [],
};

/** Pantalla del grafo de contexto persistido en S3 por el Context Builder. */
export function GraphPage() {
  const { selectedRepo } = useStore();
  const { p } = useTheme();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Tipos de nodo apagados desde la leyenda (chips-filtro): se ocultan del
  // grafo hasta que se vuelvan a activar.
  const [hiddenKinds, setHiddenKinds] = useState<Set<NodeKind>>(() => new Set());

  const [graph, setGraph] = useState<RepoGraph>(EMPTY_GRAPH);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    if (!selectedRepo) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotFound(false);
    fetchGraph(selectedRepo)
      .then((data) => {
        if (!cancelled) setGraph(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setGraph(EMPTY_GRAPH);
        if (err instanceof ApiRequestError && err.status === 404) {
          // Esperado: el Context Builder aún no generó el grafo de este repo
          // (sin revisiones procesadas todavía, o corrió en modo diff-only).
          setNotFound(true);
          setError(null);
        } else {
          setNotFound(false);
          setError(
            err instanceof ApiRequestError
              ? err.message
              : "No se pudo cargar el grafo de contexto para este repositorio.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRepo, retryToken]);

  const counts = useMemo(() => {
    const c: Record<NodeKind, number> = { module: 0, class: 0, function: 0, method: 0 };
    for (const n of graph.nodes) c[n.kind] += 1;
    return c;
  }, [graph]);

  const toggleKind = (k: NodeKind) => {
    const isCurrentlyHidden = hiddenKinds.has(k);
    setHiddenKinds((prev) => {
      const next = new Set(prev);
      if (isCurrentlyHidden) next.delete(k);
      else next.add(k);
      return next;
    });
    // Si se está ocultando este tipo y el nodo seleccionado es de ese tipo,
    // limpia la selección para que el panel de detalle no quede "huérfano".
    if (!isCurrentlyHidden) {
      setSelectedId((id) => {
        const node = id ? graph.nodes.find((n) => n.id === id) : null;
        return node?.kind === k ? null : id;
      });
    }
  };

  const selectedNode = graph.nodes.find((n) => n.id === selectedId) ?? null;
  const selectedEdges = selectedNode
    ? graph.links.filter((l) => l.source === selectedId || l.target === selectedId)
    : [];

  return (
    <>
      <Header
        repo={selectedRepo}
        title="Grafo de contexto"
        subtitle="Mapa persistente del repo: módulos, símbolos y sus relaciones"
      />

      {notFound ? (
        <Panel className="mb-4">
          <div className="flex flex-col items-start gap-3 py-4">
            <div className="flex items-center gap-2 text-muted">
              <Workflow size={18} />
              <span className="font-semibold text-ink">Aún no hay grafo de contexto</span>
            </div>
            <p className="text-sm text-muted">
              Este repositorio todavía no tiene un grafo generado. Se crea automáticamente
              cuando el pipeline procesa con éxito su primera revisión.
            </p>
            <button onClick={() => setRetryToken((t) => t + 1)} className="btn-ghost">
              <RefreshCw size={14} />
              Reintentar
            </button>
          </div>
        </Panel>
      ) : error ? (
        <Panel className="mb-4">
          <div className="flex flex-col items-start gap-3 py-4">
            <div className="flex items-center gap-2 text-high">
              <TriangleAlert size={18} />
              <span className="font-semibold">No se pudo cargar el grafo</span>
            </div>
            <p className="text-sm text-muted">{error}</p>
            <button onClick={() => setRetryToken((t) => t + 1)} className="btn-primary">
              <RefreshCw size={14} />
              Reintentar
            </button>
          </div>
        </Panel>
      ) : loading ? (
        <Panel className="mb-4">
          <p className="py-10 text-center text-sm text-muted">Cargando grafo de contexto…</p>
        </Panel>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat icon={Boxes} label="Nodos" value={graph.nodes.length} />
            <Stat icon={Workflow} label="Relaciones" value={graph.links.length} />
            <Stat icon={GitBranch} label="Versión" value={graph.graph_version} mono />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        {/* Grafo */}
        <div className="lg:col-span-3">
          <Panel
            title="Estructura del repositorio"
            subtitle="Zoom con la rueda · arrastra el fondo para desplazar · arrastra nodos · pasa el cursor para resaltar"
            action={
              <div className="flex flex-wrap gap-1.5">
                {(Object.keys(NODE_KIND_LABEL) as NodeKind[]).map((k) => {
                  const off = hiddenKinds.has(k);
                  const color = nodeKindColor(p, k);
                  return (
                    <button
                      key={k}
                      onClick={() => toggleKind(k)}
                      title={off ? `Mostrar ${NODE_KIND_LABEL[k]}` : `Ocultar ${NODE_KIND_LABEL[k]}`}
                      className={`focus-ring flex items-center gap-1.5 rounded-full px-1.5 py-1 text-[0.72rem] font-medium transition-colors ${
                        off ? "text-faint" : "text-muted hover:text-ink"
                      }`}
                    >
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: off ? "var(--faint)" : color, opacity: off ? 0.5 : 1 }}
                      />
                      {NODE_KIND_LABEL[k]}
                      <span className="text-faint">{counts[k]}</span>
                    </button>
                  );
                })}
              </div>
            }
          >
            <div className="overflow-hidden rounded-xl border border-border bg-bg">
              <GraphView
                graph={graph}
                selectedId={selectedId}
                onSelect={setSelectedId}
                hiddenKinds={hiddenKinds}
              />
            </div>
          </Panel>
        </div>

        {/* Detalle del nodo */}
        <Panel title="Detalle del nodo">
          {!selectedNode ? (
            <div className="flex h-full flex-col items-center justify-center py-16 text-center">
              <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-faint">
                <Workflow size={22} />
              </div>
              <p className="mt-3 text-sm font-medium text-muted">Selecciona un nodo</p>
              <p className="mt-1 text-xs text-faint">
                Haz clic en un nodo para ver su archivo y relaciones.
              </p>
            </div>
          ) : (
            <div className="animate-fade-up space-y-4">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ background: nodeKindColor(p, selectedNode.kind) }}
                  />
                  <span className="text-[0.7rem] font-semibold uppercase tracking-wider text-faint">
                    {NODE_KIND_LABEL[selectedNode.kind]}
                  </span>
                </div>
                <h3 className="mt-1.5 break-all text-base font-bold text-ink">{selectedNode.name}</h3>
                {selectedNode.signature && (
                  <code className="mt-1 block font-mono text-xs text-muted">
                    {selectedNode.signature}
                  </code>
                )}
              </div>

              <div className="space-y-1.5 text-xs">
                <Row label="Archivo" value={`${selectedNode.file}:${selectedNode.line_start}`} mono />
                <Row
                  label="Docstring"
                  value={selectedNode.docstring_present ? "presente" : "ausente"}
                />
                <Row label="Relaciones" value={String(selectedEdges.length)} />
              </div>

              <div>
                <div className="mb-1.5 text-[0.7rem] font-semibold uppercase tracking-wider text-faint">
                  Conexiones
                </div>
                <div className="max-h-[260px] space-y-1 overflow-y-auto pr-1">
                  {selectedEdges.map((l, i) => {
                    const outgoing = l.source === selectedId;
                    const otherId = outgoing ? l.target : l.source;
                    const other = graph.nodes.find((n) => n.id === otherId);
                    return (
                      <button
                        key={i}
                        onClick={() => setSelectedId(otherId)}
                        className="focus-ring flex w-full items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-border"
                      >
                        <span className="text-faint">{outgoing ? "→" : "←"}</span>
                        <span className="font-mono text-accent">{LINK_TYPE_LABEL[l.type]}</span>
                        <span className="min-w-0 flex-1 truncate text-ink">{other?.name}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </Panel>
          </div>
        </>
      )}
    </>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: typeof Boxes;
  label: string;
  value: string | number;
  mono?: boolean;
}) {
  return (
    <div className="panel flex items-center gap-3 p-4">
      <span className="grid h-9 w-9 place-items-center rounded-lg bg-surface-2 text-accent">
        <Icon size={17} />
      </span>
      <div>
        <div className="text-[0.72rem] font-semibold uppercase tracking-wider text-muted">
          {label}
        </div>
        <div className={`text-lg font-extrabold text-ink ${mono ? "font-mono text-sm" : ""}`}>
          {value}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted">{label}</span>
      <span className={`text-ink ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}
