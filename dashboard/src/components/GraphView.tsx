import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { nodeKindColor } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import type { NodeKind, RepoGraph } from "@/lib/types";

const VW = 900;
const VH = 560;
const MIN_K = 0.4;
const MAX_K = 3.2;

interface SimNode {
  id: string;
  kind: NodeKind;
  name: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  fixed: boolean;
}

interface View {
  x: number;
  y: number;
  k: number;
}

const RADIUS: Record<NodeKind, number> = { module: 9, class: 7, function: 5.5, method: 4.5 };

interface GraphViewProps {
  graph: RepoGraph;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Grafo dirigido por fuerzas en SVG puro con comportamiento de mapa:
 * zoom con la rueda (hacia el cursor), pan arrastrando el fondo, arrastre de
 * nodos y resaltado de vecinos. Simulación propia vía requestAnimationFrame.
 */
export function GraphView({ graph, selectedId, onSelect }: GraphViewProps) {
  const { p } = useTheme();
  const svgRef = useRef<SVGSVGElement>(null);
  const gRef = useRef<SVGGElement>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const alphaRef = useRef(1);
  const rafRef = useRef<number>(0);
  const dragRef = useRef<string | null>(null);
  const viewRef = useRef<View>({ x: 0, y: 0, k: 1 });
  const panRef = useRef<{ active: boolean; lastX: number; lastY: number; moved: boolean }>({
    active: false,
    lastX: 0,
    lastY: 0,
    moved: false,
  });
  const [, setTick] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);
  const render = useCallback(() => setTick((t) => t + 1), []);

  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const n of graph.nodes) map.set(n.id, new Set());
    for (const l of graph.links) {
      map.get(l.source)?.add(l.target);
      map.get(l.target)?.add(l.source);
    }
    return map;
  }, [graph]);

  // --- Simulación de fuerzas ---
  const tickSim = useCallback(() => {
    const nodes = nodesRef.current;
    const alpha = alphaRef.current;
    const byId = new Map(nodes.map((nd) => [nd.id, nd]));

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) {
          dx = Math.random() - 0.5;
          dy = Math.random() - 0.5;
          d2 = 0.01;
        }
        const dist = Math.sqrt(d2);
        const force = (2600 / d2) * alpha;
        a.vx += (dx / dist) * force;
        a.vy += (dy / dist) * force;
        b.vx -= (dx / dist) * force;
        b.vy -= (dy / dist) * force;
      }
    }

    for (const l of graph.links) {
      const a = byId.get(l.source);
      const b = byId.get(l.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const k = (dist - 78) * 0.015 * alpha;
      a.vx += (dx / dist) * k;
      a.vy += (dy / dist) * k;
      b.vx -= (dx / dist) * k;
      b.vy -= (dy / dist) * k;
    }

    for (const nd of nodes) {
      nd.vx += (VW / 2 - nd.x) * 0.006 * alpha;
      nd.vy += (VH / 2 - nd.y) * 0.006 * alpha;
      if (nd.fixed) {
        nd.vx = 0;
        nd.vy = 0;
        continue;
      }
      nd.vx *= 0.86;
      nd.vy *= 0.86;
      nd.x += nd.vx;
      nd.y += nd.vy;
    }

    alphaRef.current = Math.max(0, alpha - 0.008);
  }, [graph]);

  const startLoop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    const loop = () => {
      tickSim();
      render();
      if (alphaRef.current > 0.01 || dragRef.current) {
        rafRef.current = requestAnimationFrame(loop);
      }
    };
    rafRef.current = requestAnimationFrame(loop);
  }, [tickSim, render]);

  const reheat = useCallback(() => {
    alphaRef.current = Math.max(alphaRef.current, 0.4);
    startLoop();
  }, [startLoop]);

  // Inicializa nodos al cambiar el grafo.
  useEffect(() => {
    const n = graph.nodes.length;
    nodesRef.current = graph.nodes.map((node, i) => {
      const angle = (i / n) * Math.PI * 2;
      const radius = 150 + (i % 5) * 22;
      return {
        id: node.id,
        kind: node.kind,
        name: node.name,
        x: VW / 2 + Math.cos(angle) * radius,
        y: VH / 2 + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        r: RADIUS[node.kind],
        fixed: false,
      };
    });
    viewRef.current = { x: 0, y: 0, k: 1 };
    alphaRef.current = 1;
    startLoop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  // --- Conversión de coordenadas ---
  // Puntero → coords del viewBox (antes de la transform del grupo).
  const toViewBox = (clientX: number, clientY: number) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: loc.x, y: loc.y };
  };
  // Puntero → coords del mundo (dentro del grupo con zoom/pan).
  const toWorld = (clientX: number, clientY: number) => {
    const g = gRef.current!;
    const pt = svgRef.current!.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const loc = pt.matrixTransform(g.getScreenCTM()!.inverse());
    return { x: loc.x, y: loc.y };
  };

  // --- Zoom (rueda, hacia el cursor) con listener no-pasivo ---
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const vb = toViewBox(e.clientX, e.clientY);
      const view = viewRef.current;
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const k = Math.max(MIN_K, Math.min(MAX_K, view.k * factor));
      // Mantén fijo el punto bajo el cursor.
      const wx = (vb.x - view.x) / view.k;
      const wy = (vb.y - view.y) / view.k;
      viewRef.current = { k, x: vb.x - wx * k, y: vb.y - wy * k };
      render();
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Zoom por botones / ajustar ---
  const zoomBy = (factor: number) => {
    const view = viewRef.current;
    const k = Math.max(MIN_K, Math.min(MAX_K, view.k * factor));
    const cx = VW / 2;
    const cy = VH / 2;
    const wx = (cx - view.x) / view.k;
    const wy = (cy - view.y) / view.k;
    viewRef.current = { k, x: cx - wx * k, y: cy - wy * k };
    render();
  };

  const fit = useCallback(() => {
    const nodes = nodesRef.current;
    if (nodes.length === 0) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const nd of nodes) {
      minX = Math.min(minX, nd.x);
      minY = Math.min(minY, nd.y);
      maxX = Math.max(maxX, nd.x);
      maxY = Math.max(maxY, nd.y);
    }
    const pad = 60;
    const w = maxX - minX + pad * 2;
    const h = maxY - minY + pad * 2;
    const k = Math.max(MIN_K, Math.min(MAX_K, Math.min(VW / w, VH / h)));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    viewRef.current = { k, x: VW / 2 - cx * k, y: VH / 2 - cy * k };
    render();
  }, [render]);

  // --- Interacción de nodos ---
  const onNodePointerDown = (id: string) => (e: React.PointerEvent) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = id;
    const node = nodesRef.current.find((nd) => nd.id === id);
    if (node) node.fixed = true;
    onSelect(id);
    reheat();
  };

  // --- Pan del fondo ---
  const onBgPointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY, moved: false };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (dragRef.current) {
      const node = nodesRef.current.find((nd) => nd.id === dragRef.current);
      if (!node) return;
      const { x, y } = toWorld(e.clientX, e.clientY);
      node.x = x;
      node.y = y;
      node.vx = 0;
      node.vy = 0;
      render();
      return;
    }
    if (panRef.current.active) {
      const dx = e.clientX - panRef.current.lastX;
      const dy = e.clientY - panRef.current.lastY;
      // Convierte el delta de pantalla a unidades de viewBox.
      const rect = svgRef.current!.getBoundingClientRect();
      const sx = VW / rect.width;
      const sy = VH / rect.height;
      viewRef.current = {
        ...viewRef.current,
        x: viewRef.current.x + dx * sx,
        y: viewRef.current.y + dy * sy,
      };
      panRef.current.lastX = e.clientX;
      panRef.current.lastY = e.clientY;
      panRef.current.moved = true;
      render();
    }
  };

  const endInteraction = () => {
    if (dragRef.current) {
      const node = nodesRef.current.find((nd) => nd.id === dragRef.current);
      if (node) node.fixed = false;
      dragRef.current = null;
      reheat();
    }
    if (panRef.current.active) {
      // Un clic sin arrastre en el fondo deselecciona.
      if (!panRef.current.moved) onSelect(null);
      panRef.current.active = false;
    }
  };

  const active = hovered ?? selectedId;
  const neighbors = active ? adjacency.get(active) : null;
  const isDimmed = (id: string) =>
    active != null && id !== active && !(neighbors?.has(id) ?? false);

  const nodes = nodesRef.current;
  const byId = new Map(nodes.map((nd) => [nd.id, nd]));
  const { x, y, k } = viewRef.current;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        className={`h-[560px] w-full touch-none select-none ${
          panRef.current.active ? "cursor-grabbing" : "cursor-grab"
        }`}
        onPointerDown={onBgPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endInteraction}
        onPointerLeave={endInteraction}
      >
        {/* Fondo captor de eventos (pan) */}
        <rect x={0} y={0} width={VW} height={VH} fill="transparent" />

        <g ref={gRef} transform={`translate(${x} ${y}) scale(${k})`}>
          {/* Aristas */}
          <g>
            {graph.links.map((l, i) => {
              const a = byId.get(l.source);
              const b = byId.get(l.target);
              if (!a || !b) return null;
              const linkActive = active != null && (l.source === active || l.target === active);
              const dim = active != null && !linkActive;
              return (
                <line
                  key={i}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={linkActive ? p.accent : p.border}
                  strokeWidth={linkActive ? 1.6 : 1}
                  strokeDasharray={l.type === "inherits" ? "4 3" : undefined}
                  style={{
                    opacity: dim ? 0.12 : 0.7,
                    transition: "opacity .25s ease, stroke .25s ease",
                  }}
                />
              );
            })}
          </g>

          {/* Nodos */}
          <g>
            {nodes.map((nd, i) => {
              const color = nodeKindColor(p, nd.kind);
              const dim = isDimmed(nd.id);
              const isActive = nd.id === active;
              const showLabel =
                nd.kind === "module" || isActive || (neighbors?.has(nd.id) ?? false);
              return (
                <g
                  key={nd.id}
                  transform={`translate(${nd.x} ${nd.y})`}
                  className="graph-node cursor-pointer"
                  style={{
                    animationDelay: `${Math.min(i * 18, 500)}ms`,
                    opacity: dim ? 0.25 : 1,
                    transition: "opacity .25s ease",
                  }}
                  onPointerDown={onNodePointerDown(nd.id)}
                  onPointerEnter={() => setHovered(nd.id)}
                  onPointerLeave={() => setHovered(null)}
                >
                  {isActive && (
                    <circle r={nd.r + 5} fill="none" stroke={color} strokeWidth={1.5} opacity={0.4} />
                  )}
                  <circle r={nd.r} fill={color} stroke={p.bg} strokeWidth={1.5} />
                  {showLabel && (
                    <text
                      x={nd.r + 4}
                      y={3.5}
                      fontSize={nd.kind === "module" ? 11 : 9.5}
                      fontWeight={nd.kind === "module" ? 700 : 500}
                      fill={isActive ? p.ink : p.muted}
                      style={{ pointerEvents: "none" }}
                    >
                      {nd.name}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* Controles de zoom */}
      <div className="absolute bottom-3 right-3 flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card">
        <CtrlBtn onClick={() => zoomBy(1.25)} title="Acercar">
          <Plus size={15} />
        </CtrlBtn>
        <div className="h-px bg-border" />
        <CtrlBtn onClick={() => zoomBy(1 / 1.25)} title="Alejar">
          <Minus size={15} />
        </CtrlBtn>
        <div className="h-px bg-border" />
        <CtrlBtn onClick={fit} title="Ajustar a la vista">
          <Maximize2 size={14} />
        </CtrlBtn>
      </div>

      <div className="pointer-events-none absolute left-3 top-3 text-[0.68rem] text-faint">
        Rueda para zoom · arrastra el fondo para desplazar
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
