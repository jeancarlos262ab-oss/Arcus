import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { Maximize2, Minus, Plus } from "lucide-react";
import { alpha, nodeKindColor } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import type { NodeKind, RepoGraph } from "@/lib/types";

/** Nodo aumentado para el grafo (react-force-graph muta x/y/vx/vy). */
interface GNode {
  id: string;
  kind: NodeKind;
  name: string;
  val: number;
  x?: number;
  y?: number;
}
interface GLink {
  source: string;
  target: string;
  type: string;
}

const RADIUS: Record<NodeKind, number> = { module: 6, class: 4.5, function: 3.6, method: 3 };

interface GraphViewProps {
  graph: RepoGraph;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Vista de grafo estilo Obsidian con `react-force-graph-2d` (Canvas + d3-force).
 * Física de gravedad/rebote, arrastre de nodos y zoom/pan nativos de alto
 * rendimiento. El dibujo de nodos y el resaltado de vecinos son personalizados
 * y siguen el tema activo (claro/oscuro).
 */
export function GraphView({ graph, selectedId, onSelect }: GraphViewProps) {
  const { p, resolved } = useTheme();
  const fgRef = useRef<ForceGraphMethods<GNode, GLink>>();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 560 });
  const [hovered, setHovered] = useState<string | null>(null);

  // Datos en el formato de la librería. Se clonan para que la simulación mute
  // sus propias copias (no los datos del store).
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map<GNode>((n) => ({
        id: n.id,
        kind: n.kind,
        name: n.name,
        val: RADIUS[n.kind],
      })),
      links: graph.links.map<GLink>((l) => ({
        source: l.source,
        target: l.target,
        type: l.type,
      })),
    }),
    [graph],
  );

  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const n of graph.nodes) map.set(n.id, new Set());
    for (const l of graph.links) {
      map.get(l.source)?.add(l.target);
      map.get(l.target)?.add(l.source);
    }
    return map;
  }, [graph]);

  // Tamaño responsivo del contenedor.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect;
      setSize({ w: Math.round(cr.width), h: Math.round(cr.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Física estilo Obsidian + encuadre inicial.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-150);
    fg.d3Force("link")?.distance(42);
    const t = setTimeout(() => fg.zoomToFit(500, 50), 400);
    return () => clearTimeout(t);
  }, [graph]);

  // Al cambiar de tema, reactiva la simulación para repintar con los colores
  // nuevos sin perder las posiciones actuales.
  useEffect(() => {
    fgRef.current?.d3ReheatSimulation();
  }, [resolved]);

  const active = hovered ?? selectedId;
  const neighbors = active ? adjacency.get(active) : null;

  const isDim = useCallback(
    (id: string) => active != null && id !== active && !(neighbors?.has(id) ?? false),
    [active, neighbors],
  );

  const zoomBy = (factor: number) => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.zoom(fg.zoom() * factor, 220);
  };
  const fit = () => fgRef.current?.zoomToFit(400, 50);

  return (
    <div ref={wrapRef} className="relative h-[560px] w-full">
      <ForceGraph2D<GNode, GLink>
        ref={fgRef}
        width={size.w}
        height={size.h}
        graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={120}
        d3VelocityDecay={0.3}
        nodeRelSize={1}
        nodeVal={(n) => n.val}
        onNodeHover={(n) => setHovered(n ? n.id : null)}
        onNodeClick={(n) => onSelect(n.id)}
        onBackgroundClick={() => onSelect(null)}
        linkColor={(l) => {
          const s = typeof l.source === "object" ? (l.source as GNode).id : (l.source as string);
          const t = typeof l.target === "object" ? (l.target as GNode).id : (l.target as string);
          const on = active != null && (s === active || t === active);
          if (on) return p.accent;
          return active != null ? alpha(p.border, 0.35) : alpha(p.border, 0.9);
        }}
        linkWidth={(l) => {
          const s = typeof l.source === "object" ? (l.source as GNode).id : (l.source as string);
          const t = typeof l.target === "object" ? (l.target as GNode).id : (l.target as string);
          return active != null && (s === active || t === active) ? 1.6 : 0.8;
        }}
        linkDirectionalParticles={(l) => {
          const s = typeof l.source === "object" ? (l.source as GNode).id : (l.source as string);
          const t = typeof l.target === "object" ? (l.target as GNode).id : (l.target as string);
          return active != null && (s === active || t === active) ? 2 : 0;
        }}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleColor={() => p.accent}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const n = node as GNode;
          const r = n.val;
          const dim = isDim(n.id);
          const isActive = n.id === active;
          const color = nodeKindColor(p, n.kind);

          // Halo del nodo activo
          if (isActive) {
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, r + 3, 0, 2 * Math.PI);
            ctx.fillStyle = alpha(color, 0.25);
            ctx.fill();
          }

          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = dim ? alpha(color, 0.25) : color;
          ctx.fill();
          ctx.lineWidth = 0.6;
          ctx.strokeStyle = p.bg;
          ctx.stroke();

          // Etiqueta: módulos siempre; el resto al acercar o al resaltar.
          const showLabel =
            n.kind === "module" || isActive || (neighbors?.has(n.id) ?? false) || globalScale > 2.2;
          if (showLabel && !dim) {
            const fontSize = Math.max(2.5, (n.kind === "module" ? 4.2 : 3.4));
            ctx.font = `${n.kind === "module" ? 700 : 500} ${fontSize}px Inter, sans-serif`;
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillStyle = isActive ? p.ink : p.muted;
            ctx.fillText(n.name, n.x! + r + 1.5, n.y!);
          }
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          const n = node as GNode;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, n.val + 2, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
      />

      {/* Controles de zoom */}
      <div className="absolute bottom-3 right-3 flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card">
        <CtrlBtn onClick={() => zoomBy(1.3)} title="Acercar">
          <Plus size={15} />
        </CtrlBtn>
        <div className="h-px bg-border" />
        <CtrlBtn onClick={() => zoomBy(1 / 1.3)} title="Alejar">
          <Minus size={15} />
        </CtrlBtn>
        <div className="h-px bg-border" />
        <CtrlBtn onClick={fit} title="Ajustar a la vista">
          <Maximize2 size={14} />
        </CtrlBtn>
      </div>

      <div className="pointer-events-none absolute left-3 top-3 text-[0.68rem] text-faint">
        Rueda para zoom · arrastra el fondo para desplazar · arrastra nodos
      </div>
    </div>
  );
}

function CtrlBtn({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="focus-ring grid h-8 w-8 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {children}
    </button>
  );
}
