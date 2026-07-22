import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { PALETTES, type Palette, type ResolvedTheme, type ThemeMode } from "@/lib/theme";

const STORAGE_KEY = "arcus.theme";

interface ThemeContextValue {
  /** Modo elegido por el usuario: light | dark | system. */
  mode: ThemeMode;
  /** Tema efectivo tras resolver "system". */
  resolved: ResolvedTheme;
  /** Paleta de color activa (para Recharts / SVG). */
  p: Palette;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolve(mode: ThemeMode): ResolvedTheme {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    return stored ?? "dark";
  });
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(mode));

  // Aplica la clase al <html> antes de pintar para evitar parpadeo.
  useLayoutEffect(() => {
    const r = resolve(mode);
    setResolved(r);
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(r);
  }, [mode]);

  // Reacciona a cambios del SO cuando el modo es "system".
  useEffect(() => {
    if (mode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const r = systemPrefersDark() ? "dark" : "light";
      setResolved(r);
      document.documentElement.classList.remove("light", "dark");
      document.documentElement.classList.add(r);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    localStorage.setItem(STORAGE_KEY, next);
    setModeState(next);
  }, []);

  const toggle = useCallback(() => {
    setMode(resolved === "dark" ? "light" : "dark");
  }, [resolved, setMode]);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, resolved, p: PALETTES[resolved], setMode, toggle }),
    [mode, resolved, setMode, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>");
  return ctx;
}
