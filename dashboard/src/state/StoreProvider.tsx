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
const HIDDEN_REPOS_KEY = "arcus.hiddenRepos.v1";
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
 * Repos "vigilados" agregados manualmente desde Ajustes, guardados en el
 * navegador. Permiten preparar un repositorio en el dashboard antes de que
 * el pipeline registre su primera revisión real; no sustituyen los datos
 * reales, solo amplían qué aparece en el selector mientras llegan.
 */
function loadWatchlist(): string[] {
  return loadStringList(WATCHLIST_KEY);
}

function saveWatchlist(repos: string[]): void {
  saveStringList(WATCHLIST_KEY, repos);
}

/**
 * Repos con historial real que el usuario ocultó individualmente (o vía
 * "Desconectar todo"). Es una preferencia local por repo, no un interruptor
 * global: agregar OTRO repo nunca revive uno que ya se ocultó a propósito.
 */
function loadHiddenRepos(): string[] {
  return loadStringList(HIDDEN_REPOS_KEY);
}

function saveHiddenRepos(repos: string[]): void {
  saveStringList(HIDDEN_REPOS_KEY, repos);
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
  /** Agrega un repo a la watchlist local (owner/repo). No crea datos falsos. */
  addRepo: (fullName: string) => { ok: boolean; error?: string };
  /**
   * Quita un repo de la vista: si es de la watchlist local lo borra; si es un
   * repo real con historial, lo oculta individualmente (no borra nada en
   * DynamoDB/S3). Nunca reaparece solo por agregar otro repo distinto.
   */
  removeRepo: (fullName: string) => void;
  /**
   * Desconecta todo: oculta cada repo visible ahora mismo (real o local) y
   * deja el dashboard como recién instalado. No borra historial en
   * DynamoDB/S3 ni desinstala la GitHub App.
   */
  disconnectAll: () => void;
  /** Repos agregados manualmente que aún no tienen historial real. */
  watchedRepos: string[];
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
  const [hiddenRepos, setHiddenRepos] = useState<string[]>(loadHiddenRepos);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [rangeKey, setRangeKey] = useState<RangeKey>("90d");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const apiRepos = await fetchRepos();
        if (apiRepos.length === 0) {
          if (!cancelled) {
            setState({ loading: false, error: null, apiRepos: [], runs: [], findingsByRun: {} });
          }
          return;
        }

        const reviewsByRepo = await Promise.all(apiRepos.map((repo) => fetchReviews(repo)));
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
  }, [reloadToken]);

  // Repos visibles = los que ya tienen historial real + los vigilados manualmente,
  // menos los que el usuario ocultó individualmente (por repo, no global).
  const repos = useMemo(() => {
    const merged = new Set([...state.apiRepos, ...watchlist]);
    for (const hidden of hiddenRepos) merged.delete(hidden);
    return [...merged].sort();
  }, [state.apiRepos, watchlist, hiddenRepos]);

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
      if (repos.includes(name)) {
        return { ok: false, error: "El repositorio ya está en la lista." };
      }
      // Agregar un repo que estaba oculto es un acto de reconexión explícito
      // para ESE repo puntual; no afecta a ningún otro repo oculto.
      setHiddenRepos((current) => {
        if (!current.includes(name)) return current;
        const next = current.filter((r) => r !== name);
        saveHiddenRepos(next);
        return next;
      });
      if (!state.apiRepos.includes(name)) {
        setWatchlist((current) => {
          if (current.includes(name)) return current;
          const next = [...current, name];
          saveWatchlist(next);
          return next;
        });
      }
      return { ok: true };
    },
    [repos, state.apiRepos],
  );

  const removeRepo = useCallback((fullName: string) => {
    setWatchlist((current) => {
      if (!current.includes(fullName)) return current;
      const next = current.filter((r) => r !== fullName);
      saveWatchlist(next);
      return next;
    });
    // Si además tiene historial real, ocúltalo individualmente; agregar otro
    // repo distinto nunca lo va a revivir por accidente.
    setHiddenRepos((current) => {
      if (current.includes(fullName)) return current;
      const next = [...current, fullName];
      saveHiddenRepos(next);
      return next;
    });
  }, []);

  /**
   * Oculta cada repo visible ahora mismo (real u observado localmente) y
   * vacía la watchlist. No toca DynamoDB/S3 ni la instalación de la GitHub
   * App en GitHub; cada repo puede volver a agregarse individualmente.
   */
  const disconnectAll = useCallback(() => {
    setWatchlist([]);
    saveWatchlist([]);
    setHiddenRepos((current) => {
      const next = [...new Set([...current, ...repos])];
      saveHiddenRepos(next);
      return next;
    });
    setSelectedRepo("");
  }, [repos]);

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
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore debe usarse dentro de <StoreProvider>");
  return ctx;
}
