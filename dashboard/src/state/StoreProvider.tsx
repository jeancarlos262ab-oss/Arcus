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
  repos: string[];
  runs: ReviewRun[];
  findingsByRun: Record<string, Finding[]>;
}

const INITIAL_STATE: StoreState = {
  loading: true,
  error: null,
  repos: [],
  runs: [],
  findingsByRun: {},
};

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
}

const StoreContext = createContext<StoreContextValue | null>(null);

/**
 * Carga y expone datos reales del backend de Arcus (DynamoDB vía la API de
 * solo lectura). No hay generación local ni simulación: si la API falla, el
 * estado queda en `error` y la UI lo muestra explícitamente.
 */
export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StoreState>(INITIAL_STATE);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [rangeKey, setRangeKey] = useState<RangeKey>("90d");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const repos = await fetchRepos();
        if (repos.length === 0) {
          if (!cancelled) {
            setState({ loading: false, error: null, repos: [], runs: [], findingsByRun: {} });
          }
          return;
        }

        const reviewsByRepo = await Promise.all(repos.map((repo) => fetchReviews(repo)));
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
          setState({ loading: false, error: null, repos, runs, findingsByRun });
          setSelectedRepo((current) => (repos.includes(current) ? current : repos[0]));
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

  const getFindings = useCallback(
    (runId: string) => state.findingsByRun[runId] ?? [],
    [state.findingsByRun],
  );

  const refresh = useCallback(() => setReloadToken((t) => t + 1), []);

  const settings = useMemo<DisplaySettings>(
    () => ({ region: RUNTIME_CONFIG.region, modelId: RUNTIME_CONFIG.modelId }),
    [],
  );

  const value = useMemo<StoreContextValue>(
    () => ({
      loading: state.loading,
      error: state.error,
      repos: state.repos,
      runs: state.runs,
      settings,
      selectedRepo,
      rangeKey,
      setSelectedRepo,
      setRangeKey,
      getFindings,
      refresh,
    }),
    [
      state.loading,
      state.error,
      state.repos,
      state.runs,
      settings,
      selectedRepo,
      rangeKey,
      getFindings,
      refresh,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore debe usarse dentro de <StoreProvider>");
  return ctx;
}
