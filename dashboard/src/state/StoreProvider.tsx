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
import { fetchMyWatchlist, saveMyWatchlist } from "@/lib/authApi";
import { RUNTIME_CONFIG } from "@/lib/runtimeConfig";
import { useAuth } from "@/state/AuthProvider";
import type { Finding, ReviewRun } from "@/lib/types";

export type RangeKey = "30d" | "60d" | "90d";

interface DisplaySettings {
  region: string;
  modelId: string;
}

interface StoreState {
  loading: boolean;
  error: string | null;
  /** La selección del usuario logueado, leída de su cuenta (no del navegador). */
  watchlist: string[];
  /** Repos con al menos una revisión real en DynamoDB, entre todos los usuarios. */
  apiRepos: string[];
  runs: ReviewRun[];
  findingsByRun: Record<string, Finding[]>;
}

const INITIAL_STATE: StoreState = {
  loading: true,
  error: null,
  watchlist: [],
  apiRepos: [],
  runs: [],
  findingsByRun: {},
};

const REPO_PATTERN = /^[\w.-]+\/[\w.-]+$/;

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
  /** Vuelve a cargar la selección y las revisiones desde la cuenta del usuario. */
  refresh: () => void;
  /**
   * Elige un repo para verlo (owner/repo), guardado en la cuenta de GitHub del
   * usuario logueado. No crea datos falsos: solo agrega el nombre a su
   * selección, con o sin historial real todavía.
   */
  addRepo: (fullName: string) => Promise<{ ok: boolean; error?: string }>;
  /** Quita un repo de la selección del usuario. No borra nada en DynamoDB/S3. */
  removeRepo: (fullName: string) => Promise<void>;
  /** Vacía la selección del usuario por completo. */
  disconnectAll: () => Promise<void>;
  /** Repos que la selección del usuario incluye. Puede tener 0, 1 o más elementos. */
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
 * solo lectura) para el usuario logueado. La selección de repos vive en la
 * cuenta de GitHub del usuario (vía `auth_api`), no en `localStorage`: cambia
 * de navegador o de dispositivo y sigue siendo la misma. No hay generación
 * local ni simulación: si la API falla, el estado queda en `error`.
 */
export function StoreProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [state, setState] = useState<StoreState>(INITIAL_STATE);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [rangeKey, setRangeKey] = useState<RangeKey>("90d");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!user) {
      setState(INITIAL_STATE);
      return;
    }

    let cancelled = false;

    async function load() {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const [apiRepos, watchlist] = await Promise.all([
          fetchRepos(),
          fetchMyWatchlist(),
        ]);
        const reposToLoad = watchlist.filter((repo) => apiRepos.includes(repo));

        if (reposToLoad.length === 0) {
          if (!cancelled) {
            setState({
              loading: false,
              error: null,
              watchlist,
              apiRepos,
              runs: [],
              findingsByRun: {},
            });
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
          setState({ loading: false, error: null, watchlist, apiRepos, runs, findingsByRun });
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
  }, [reloadToken, user]);

  // Repos visibles = únicamente los que el usuario eligió en su cuenta.
  const repos = useMemo(() => [...state.watchlist].sort(), [state.watchlist]);

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
    async (fullName: string) => {
      const name = fullName.trim();
      if (!REPO_PATTERN.test(name)) {
        return { ok: false, error: "Formato inválido. Usa owner/repo." };
      }
      if (state.watchlist.includes(name)) {
        return { ok: false, error: "El repositorio ya está en tu lista." };
      }
      const saved = await saveMyWatchlist([...state.watchlist, name]);

      // Carga de inmediato las revisiones reales de este repo (si ya tiene
      // historial en el backend) en vez de esperar al próximo refresh
      // completo; evita el "aparece en 0 y luego se llena" al agregar uno.
      let newRuns: ReviewRun[] = [];
      const newFindingsByRun: Record<string, Finding[]> = {};
      if (state.apiRepos.includes(name)) {
        try {
          const reviews = await fetchReviews(name);
          for (const { findings, ...run } of reviews) {
            newRuns.push(run);
            newFindingsByRun[run.pipeline_run_id] = findings;
          }
        } catch {
          // Si falla la carga puntual, el próximo refresh la reintentará;
          // no bloquea que el repo quede agregado a la selección.
          newRuns = [];
        }
      }

      setState((s) => ({
        ...s,
        watchlist: saved,
        runs: [...s.runs, ...newRuns].sort((a, b) => a.created_at.localeCompare(b.created_at)),
        findingsByRun: { ...s.findingsByRun, ...newFindingsByRun },
      }));
      return { ok: true };
    },
    [state.watchlist, state.apiRepos],
  );

  const removeRepo = useCallback(
    async (fullName: string) => {
      if (!state.watchlist.includes(fullName)) return;
      const saved = await saveMyWatchlist(state.watchlist.filter((r) => r !== fullName));
      setState((s) => ({ ...s, watchlist: saved }));
    },
    [state.watchlist],
  );

  /** Vacía la selección del usuario por completo. */
  const disconnectAll = useCallback(async () => {
    await saveMyWatchlist([]);
    setState((s) => ({ ...s, watchlist: [] }));
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
      watchedRepos: state.watchlist,
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
      state.watchlist,
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
