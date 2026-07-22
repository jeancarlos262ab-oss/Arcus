import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/state/ThemeProvider";

/** Botón rápido para alternar claro/oscuro. */
export function ThemeToggle() {
  const { resolved, toggle } = useTheme();
  const isDark = resolved === "dark";
  return (
    <button
      onClick={toggle}
      className="focus-ring grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface text-muted transition-colors hover:text-ink"
      title={isDark ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
      aria-label="Alternar tema"
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
