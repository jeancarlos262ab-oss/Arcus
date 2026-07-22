import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { generateDataset, REPOS } from "@/lib/mockData";
import { simulateReview, type LogLine, type NewReviewInput } from "@/lib/simulate";
import type { Finding, ReviewRun, Severity } from "@/lib/types";

export type RangeKey = "30d" | "60d" | "90d";

export interface Settings {
  autoComment: boolean;
  minSeverityToComment: Severity;
  region: string;
  modelId: string;
  githubAppId: string;
  webhookConfigured: boolean;
}

const DEFAULT_SETTINGS: Settings = {
  autoComment: true,
  minSeverityToComment: "low",
  region: "us-east-1",
  modelId: "anthropic.claude-3-5-sonnet-20240620-v1:0",
  githubAppId: "",
  webhookConfigured: false,
};

interface PersistShape {
  repos: string[];
  runs: ReviewRun[];
  findingsByRun: Record<string, Finding[]>;
  settings: Settings;
}

const STORAGE_KEY = "arcus.store.v1";

function loadInitial(): PersistShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PersistShape;
      if (parsed.runs && parsed.repos) {
        return { ...parsed, settings: { ...DEFAULT_SETTINGS, ...parsed.settings } };
      }
    }
  } catch {
    // Ignora datos corruptos y re-siembra.
  }
  const ds = generateDataset();
  return {
    repos: [...REPOS],
    runs: ds.runs,
    findingsByRun: ds.findingsByRun,
    settings: DEFAULT_SETTINGS,
  };
}

interface StoreContextValue {
  repos: string[];
  runs: ReviewRun[];
  settings: Settings;
  selectedRepo: string;
  rangeKey: RangeKey;
  setSelectedRepo: (repo: string) => void;
  setRangeKey: (key: RangeKey) => void;
  getFindings: (runId: string) => Finding[];
  addRepo: (fullName: string) => { ok: boolean; error?: string };
  removeRepo: (fullName: string) => void;
  updateSettings: (patch: Partial<Settings>) => void;
  /** Ejecuta una revisión simulada, emitiendo logs; agrega el run al store. */
  runReview: (
    input: NewReviewInput,
    emit: (line: LogLine) => void,
    signal?: AbortSignal,
  ) => Promise<ReviewRun>;
  resetData: () => void;
}

const StoreContext = createContext<StoreContextValue | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PersistShape>(loadInitial);
  const [selectedRepo, setSelectedRepo] = useState<string>(() => state.repos[0] ?? "");
  const [rangeKey, setRangeKey] = useState<RangeKey>("90d");

  // Persistencia
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  // Mantén un repo válido seleccionado.
  useEffect(() => {
    if (!state.repos.includes(selectedRepo) && state.repos.length > 0) {
      setSelectedRepo(state.repos[0]);
    }
  }, [state.repos, selectedRepo]);

  const getFindings = useCallback(
    (runId: string) => state.findingsByRun[runId] ?? [],
    [state.findingsByRun],
  );

  const addRepo = useCallback((fullName: string) => {
    const name = fullName.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(name)) {
      return { ok: false, error: "Formato inválido. Usa owner/repo." };
    }
    let duplicated = false;
    setState((s) => {
      if (s.repos.includes(name)) {
        duplicated = true;
        return s;
      }
      return { ...s, repos: [...s.repos, name] };
    });
    return duplicated ? { ok: false, error: "El repositorio ya existe." } : { ok: true };
  }, []);

  const removeRepo = useCallback((fullName: string) => {
    setState((s) => {
      const runsToDrop = new Set(
        s.runs.filter((r) => r.repo_full_name === fullName).map((r) => r.pipeline_run_id),
      );
      const findingsByRun = { ...s.findingsByRun };
      for (const id of runsToDrop) delete findingsByRun[id];
      return {
        ...s,
        repos: s.repos.filter((r) => r !== fullName),
        runs: s.runs.filter((r) => r.repo_full_name !== fullName),
        findingsByRun,
      };
    });
  }, []);

  const updateSettings = useCallback((patch: Partial<Settings>) => {
    setState((s) => ({ ...s, settings: { ...s.settings, ...patch } }));
  }, []);

  const runReview = useCallback(
    async (input: NewReviewInput, emit: (line: LogLine) => void, signal?: AbortSignal) => {
      const { run, findings } = await simulateReview(input, emit, { signal });
      setState((s) => ({
        ...s,
        repos: s.repos.includes(run.repo_full_name) ? s.repos : [...s.repos, run.repo_full_name],
        runs: [...s.runs, run],
        findingsByRun: { ...s.findingsByRun, [run.pipeline_run_id]: findings },
      }));
      return run;
    },
    [],
  );

  const resetData = useCallback(() => {
    const ds = generateDataset();
    setState({
      repos: [...REPOS],
      runs: ds.runs,
      findingsByRun: ds.findingsByRun,
      settings: DEFAULT_SETTINGS,
    });
    setSelectedRepo(REPOS[0]);
  }, []);

  const value = useMemo<StoreContextValue>(
    () => ({
      repos: state.repos,
      runs: state.runs,
      settings: state.settings,
      selectedRepo,
      rangeKey,
      setSelectedRepo,
      setRangeKey,
      getFindings,
      addRepo,
      removeRepo,
      updateSettings,
      runReview,
      resetData,
    }),
    [
      state.repos,
      state.runs,
      state.settings,
      selectedRepo,
      rangeKey,
      getFindings,
      addRepo,
      removeRepo,
      updateSettings,
      runReview,
      resetData,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore debe usarse dentro de <StoreProvider>");
  return ctx;
}
