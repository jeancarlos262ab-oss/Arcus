import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { nodeKindColor } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";
import type { NodeKind, RepoGraph } from "@/lib/types";

const VW = 900;
const VH = 560;

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

const RADIUS: Record<NodeKind, number> = { module: 9, class: 7, function: 5.5, method: 4.5 };

interface GraphViewProps {
  graph: RepoGraph;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Grafo dirigido por fuerzas en SVG puro. Simulación propia (sin dependencias),
 * con arrastre de nodos, resaltado de vecinos al pasar el cursor y animación de
 * asentamiento fluida vía requestAnimationFrame.
 */
export function GraphView({ graph, selectedId, onSelect }: GraphViewProps) {
  const { p } = useTheme();
  const svgRef = useRef<SVGSVGElement>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const alphaRef = useRef(1);
  const rafRef = useRef<number>(0);
  const dragRef = useRef<string | null>(null);
  const [, setTick] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);

  // Inicializa nodos (en círculo) y adyacencia cuando cambia el grafo.
  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const n of graph.nodes) map.set(n.id, new Set());
    for (const l of graph.links) {
      map.get(l.source)?.add(l.target);
      map.get(l.target)?.add(l.source);
    }
    return map;
  }, [graph]);

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
    alphaRef.current = 1;
    startLoop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  const tickSim = useCallback(() => {
    const nodes = nodesRef.current;
    const alpha = alphaRef.current;
    const byId = new Map(nodes.map((nd) => [nd.id, nd]));

    // Repulsión entre nodos
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
        const force = (2600 / d2) * alpha;
        const dist = Math.sqrt(d2);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    // Resortes en las aristas
    for (const l of graph.links) {
      const a = byId.get(l.source);
      const b = byId.get(l.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const desired = 78;
      const k = (dist - desired) * 0.015 * alpha;
      const fx = (dx / dist) * k;
      const fy = (dy / dist) * k;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }

    // Gravedad al centro + integración
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
      nd.x = Math.max(nd.r + 6, Math.min(VW - nd.r - 6, nd.x));
      nd.y = Math.max(nd.r + 6, Math.min(VH - nd.r - 6, nd.y));
    }

    alphaRef.current = Math.max(0, alpha - 0.008);
  }, [graph]);

  const startLoop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    const loop = () => {
      tickSim();
      setTick((t) => t + 1);
      if (alphaRef.current > 0.01 || dragRef.current) {
        rafRef.current = requestAnimationFrame(loop);
      }
    };
    rafRef.current = requestAnimationFrame(loop);
  }, [tickSim]);

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  const reheat = useCallback(() => {
    alphaRef.current = Math.max(alphaRef.current, 0.4);
    startLoop();
  }, [startLoop]);

  // Convierte coordenadas de pantalla a coordenadas del viewBox.
  const toLocal = (clientX: number, clientY: number) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: loc.x, y: loc.y };
  };

  const onPointerDown = (id: string) => (e: React.PointerEvent) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = id;
    const node = nodesRef.current.find((nd) => nd.id === id);
    if (node) node.fixed = true;
    onSelect(id);
    reheat();
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const node = nodesRef.current.find((nd) => nd.id === dragRef.current);
    if (!node) return;
    const { x, y } = toLocal(e.clientX, e.clientY);
    node.x = x;
    node.y = y;
    node.vx = 0;
    node.vy = 0;
    setTick((t) => t + 1);
  };

  const onPointerUp = () => {
    if (dragRef.current) {
      const node = nodesRef.current.find((nd) => nd.id === dragRef.current);
      if (node) node.fixed = false;
      dragRef.current = null;
      reheat();
    }
  };

  const active = hovered ?? selectedId;
  const neighbors = active ? adjacency.get(active) : null;
  const isDimmed = (id: string) =>
    active != null && id !== active && !(neighbors?.has(id) ?? false);

  const nodes = nodesRef.current;
  const byId = new Map(nodes.map((nd) => [nd.id, nd]));

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${VW} ${VH}`}
      className="h-[560px] w-full touch-none select-none"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onClick={() => onSelect(null)}
    >
      {/* Aristas */}
      <g>
        {graph.links.map((l, i) => {
          const a = byId.get(l.source);
          const b = byId.get(l.target);
          if (!a || !b) return null;
          const linkActive =
            active != null && (l.source === active || l.target === active);
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
              style={{ opacity: dim ? 0.15 : 0.7, transition: "opacity .25s ease, stroke .25s ease" }}
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
          const showLabel = nd.kind === "module" || isActive || (neighbors?.has(nd.id) ?? false);
          return (
            <g
              key={nd.id}
              transform={`translate(${nd.x} ${nd.y})`}
              className="graph-node cursor-pointer"
              style={{ animationDelay: `${Math.min(i * 18, 500)}ms`, opacity: dim ? 0.25 : 1, transition: "opacity .25s ease" }}
              onPointerDown={onPointerDown(nd.id)}
              onPointerEnter={() => setHovered(nd.id)}
              onPointerLeave={() => setHovered(null)}
            >
              {isActive && (
                <circle r={nd.r + 5} fill="none" stroke={color} strokeWidth={1.5} opacity={0.4} />
              )}
              <circle
                r={nd.r}
                fill={color}
                stroke={p.bg}
                strokeWidth={1.5}
                style={{ transition: "r .2s ease" }}
              />
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
    </svg>
  );
}
