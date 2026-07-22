/**
 * Generador determinista del grafo de contexto por repositorio.
 *
 * Produce un `RepoGraph` con la forma que persiste el Context Builder en S3
 * (design.md): módulos, clases, funciones y métodos como nodos; imports, calls,
 * inherits y defines como aristas. Determinista por repo para una demo estable.
 */

import type { GraphLink, GraphNode, NodeKind, RepoGraph } from "./types";

const MODULE_NAMES = [
  "config",
  "api",
  "service",
  "models",
  "utils",
  "auth",
  "db",
  "handlers",
  "client",
];

const FN_NAMES = [
  "load",
  "validate",
  "build",
  "parse",
  "run",
  "fetch",
  "save",
  "resolve",
  "handle",
  "serialize",
  "connect",
  "query",
];

const CLASS_NAMES = ["Config", "Client", "Repository", "Service", "Model", "Handler"];

/** PRNG determinista (mulberry32) a partir de una cadena. */
function seededRng(seed: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  let a = h >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const cache = new Map<string, RepoGraph>();

/** Devuelve (memoizado) el grafo de contexto simulado de un repo. */
export function getGraph(repo: string): RepoGraph {
  const cached = cache.get(repo);
  if (cached) return cached;

  const rand = seededRng(repo);
  const pick = <T>(arr: readonly T[]): T => arr[Math.floor(rand() * arr.length)];
  const randInt = (min: number, max: number) => Math.floor(rand() * (max - min + 1)) + min;

  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];

  const nModules = randInt(5, 7);
  const modules = [...MODULE_NAMES].slice(0, nModules);
  const symbolsByModule: Record<string, string[]> = {};

  for (const mod of modules) {
    const modId = `mod:${mod}`;
    nodes.push({
      id: modId,
      kind: "module",
      file: `src/${mod}.py`,
      name: mod,
      line_start: 1,
      line_end: randInt(80, 320),
    });

    const symIds: string[] = [];
    const nSym = randInt(2, 4);
    for (let i = 0; i < nSym; i++) {
      const isClass = rand() > 0.7;
      const kind: NodeKind = isClass ? "class" : rand() > 0.5 ? "function" : "method";
      const base = isClass ? pick(CLASS_NAMES) : pick(FN_NAMES);
      const name = isClass ? base : `${base}_${mod}`;
      const symId = `sym:${mod}.${name}`;
      const line = randInt(10, 260);
      nodes.push({
        id: symId,
        kind,
        file: `src/${mod}.py`,
        name,
        line_start: line,
        line_end: line + randInt(4, 30),
        signature: isClass ? `class ${name}` : `def ${name}(...)`,
        docstring_present: rand() > 0.4,
      });
      links.push({ source: modId, target: symId, type: "defines" });
      symIds.push(symId);
    }
    symbolsByModule[mod] = symIds;
  }

  // imports entre módulos
  for (let i = 0; i < modules.length; i++) {
    const importsN = randInt(1, 2);
    for (let k = 0; k < importsN; k++) {
      const target = pick(modules);
      if (target !== modules[i]) {
        links.push({ source: `mod:${modules[i]}`, target: `mod:${target}`, type: "imports" });
      }
    }
  }

  // calls entre símbolos de módulos distintos
  const allSyms = Object.values(symbolsByModule).flat();
  const nCalls = Math.min(allSyms.length + 3, 18);
  for (let i = 0; i < nCalls; i++) {
    const a = pick(allSyms);
    const b = pick(allSyms);
    if (a !== b) links.push({ source: a, target: b, type: "calls" });
  }

  // inherits entre clases
  const classes = nodes.filter((n) => n.kind === "class").map((n) => n.id);
  if (classes.length >= 2) {
    const child = pick(classes);
    const parent = pick(classes);
    if (child !== parent) links.push({ source: child, target: parent, type: "inherits" });
  }

  const graph: RepoGraph = {
    repo,
    graph_version: `commit-${(Math.floor(rand() * 0xfffff)).toString(16)}`,
    language: "python",
    nodes,
    links,
  };
  cache.set(repo, graph);
  return graph;
}
