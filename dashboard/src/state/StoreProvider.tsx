import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiConfigError, ApiRequestError, fetchRepos, fetchReviews } from "@/lib/api";
import { RUNTIME_CONFIG } from "@/lib/runtimeConfig";
import type { Finding, ReviewRun } from "@/lib/types";

export type RangeKey = "30d" | "60d" | "90d";

interface DisplaySettings {
  region: string;
  modelId: string;
}

interface StoreState {
  loading: boolean;
  error: string | null;
  /** Repos con al menos una revisión real en DynamoDB. */
  apiRepos: string[];
  runs: ReviewRun[];
  findingsByRun: Record<string, Finding[]>;
}

const INITIAL_STATE: StoreState = {
  loading: true,
  error: null,
  apiRepos: [],
  runs: [],
  findingsByRun: {},
};

const WATCHLIST_KEY = "arcus.watchedRepos.v1";
const REPO_PATTERN = /^[\w.-]+\/[\w.-]+$/;

function loadStringList(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((r): r is string => typeof r === "string") : [];
  } catch {
    return [];
  }
}

function saveStringList(key: string, values: string[]): void {
  localStorage.setItem(key, JSON.stringify(values));
}

/**
 * Repos elegidos explícitamente por quien usa este navegador, guardados
 * localmente. El backend puede tener historial de muchos repos compartidos
 * entre todo el equipo; el dashboard nunca los muestra automáticamente,
 * cada persona elige los suyos aquí. Vacío por defecto: nada aparece hasta
 * que el usuario agrega un repo.
 */
function loadWatchlist(): string[] {
  return loadStringList(WATCHLIST_KEY);
}

function saveWatchlist(repos: string[]): void {
  saveStringList(WATCHLIST_KEY, repos);
}

interface StoreContextValue {
  loading: boolean;
  error: string | null;
  repos: string[];
  runs: ReviewRun[];
  settings: DisplaySettings;
  selectedRepo: string;
  rangeKey: RangeKey;
  setSelectedRepo: (repo: string) => void;
  setRangeKey: (key: RangeKey) => void;
  getFindings: (runId: string) => Finding[];
  /** Vuelve a cargar repos y revisiones desde la API real. */
  refresh: () => void;
  /**
   * Elige un repo para verlo en este navegador (owner/repo). No crea datos
   * falsos: solo agrega el nombre a tu lista local, con o sin historial real
   * todavía.
   */
  addRepo: (fullName: string) => { ok: boolean; error?: string };
  /** Quita un repo de tu lista local. No borra nada en DynamoDB/S3. */
  removeRepo: (fullName: string) => void;
  /** Vacía tu lista local por completo: el dashboard queda como recién instalado. */
  disconnectAll: () => void;
  /** Repos que tu lista local incluye. Puede tener 0, 1 o más elementos. */
  watchedRepos: string[];
  /**
   * Todo repo con al menos una revisión real en el backend compartido,
   * independientemente de quién lo agregó. Se usa solo como catálogo para
   * elegir (p. ej. en el modal de conectar); nunca se muestra directamente.
   */
  availableRepos: string[];
}

const StoreContext = createContext<StoreContextValue | null>(null);

/**
 * Carga y expone datos reales del backend de Arcus (DynamoDB vía la API de
 * solo lectura). No hay generación local ni simulación: si la API falla, el
 * estado queda en `error` y la UI lo muestra explícitamente.
 */
export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StoreState>(INITIAL_STATE);
  const [watchlist, setWatchlist] = useState<string[]>(loadWatchlist);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [rangeKey, setRangeKey] = useState<RangeKey>("90d");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        // El catálogo completo (qué repos tienen historial en el backend
        // compartido) solo sirve para elegir; nunca se muestra directamente.
        const apiRepos = await fetchRepos();
        const reposToLoad = watchlist.filter((repo) => apiRepos.includes(repo));

        if (reposToLoad.length === 0) {
          if (!cancelled) {
            setState({ loading: false, error: null, apiRepos, runs: [], findingsByRun: {} });
          }
          return;
        }

        const reviewsByRepo = await Promise.all(reposToLoad.map((repo) => fetchReviews(repo)));
        const runs: ReviewRun[] = [];
        const findingsByRun: Record<string, Finding[]> = {};
        for (const reviews of reviewsByRepo) {
          for (const { findings, ...run } of reviews) {
            runs.push(run);
            findingsByRun[run.pipeline_run_id] = findings;
          }
        }
        runs.sort((a, b) => a.created_at.localeCompare(b.created_at));

        if (!cancelled) {
          setState({ loading: false, error: null, apiRepos, runs, findingsByRun });
        }
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiConfigError
            ? err.message
            : err instanceof ApiRequestError
              ? err.message
              : "No se pudo cargar la información del backend de Arcus.";
        setState((s) => ({ ...s, loading: false, error: message }));
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadToken, watchlist]);

  // Repos visibles = únicamente los que el usuario eligió en este navegador.
  // Nunca se muestra automáticamente el catálogo completo del backend.
  const repos = useMemo(() => [...watchlist].sort(), [watchlist]);

  // Mantén un repo válido seleccionado en cuanto la lista combinada esté lista.
  useEffect(() => {
    if (repos.length === 0) {
      setSelectedRepo("");
      return;
    }
    setSelectedRepo((current) => (repos.includes(current) ? current : repos[0]));
  }, [repos]);

  const getFindings = useCallback(
    (runId: string) => state.findingsByRun[runId] ?? [],
    [state.findingsByRun],
  );

  const refresh = useCallback(() => setReloadToken((t) => t + 1), []);

  const addRepo = useCallback(
    (fullName: string) => {
      const name = fullName.trim();
      if (!REPO_PATTERN.test(name)) {
        return { ok: false, error: "Formato inválido. Usa owner/repo." };
      }
      if (watchlist.includes(name)) {
        return { ok: false, error: "El repositorio ya está en tu lista." };
      }
      setWatchlist((current) => {
        const next = [...current, name];
        saveWatchlist(next);
        return next;
      });
      return { ok: true };
    },
    [watchlist],
  );

  const removeRepo = useCallback((fullName: string) => {
    setWatchlist((current) => {
      if (!current.includes(fullName)) return current;
      const next = current.filter((r) => r !== fullName);
      saveWatchlist(next);
      return next;
    });
  }, []);

  /** Vacía la lista local por completo: el dashboard queda como recién instalado. */
  const disconnectAll = useCallback(() => {
    setWatchlist([]);
    saveWatchlist([]);
    setSelectedRepo("");
  }, []);

  const settings = useMemo<DisplaySettings>(
    () => ({ region: RUNTIME_CONFIG.region, modelId: RUNTIME_CONFIG.modelId }),
    [],
  );

  const value = useMemo<StoreContextValue>(
    () => ({
      loading: state.loading,
      error: state.error,
      repos,
      runs: state.runs,
      settings,
      selectedRepo,
      rangeKey,
      setSelectedRepo,
      setRangeKey,
      getFindings,
      refresh,
      addRepo,
      removeRepo,
      disconnectAll,
      watchedRepos: watchlist,
      availableRepos: state.apiRepos,
    }),
    [
      state.loading,
      state.error,
      repos,
      state.runs,
      settings,
      selectedRepo,
      rangeKey,
      getFindings,
      refresh,
      addRepo,
      removeRepo,
      disconnectAll,
      watchlist,
      state.apiRepos,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore debe usarse dentro de <StoreProvider>");
  return ctx;
}
