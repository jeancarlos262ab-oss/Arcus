import { useMemo } from "react";
import {
  Activity,
  FolderGit2,
  LayoutDashboard,
  LogOut,
  Settings,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useStore } from "@/state/StoreProvider";
import { useAuth } from "@/state/AuthProvider";
import { repoHealthSummaries } from "@/lib/selectors";
import { RepoPreviewCard } from "@/components/ui/RepoPreview";

export type PageKey = "overview" | "activity" | "graph" | "findings" | "settings";

interface SidebarProps {
  page: PageKey;
  onNavigate: (page: PageKey) => void;
  repos: string[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  /** Controla la visibilidad en móvil/tablet (off-canvas); en desktop siempre es visible. */
  open: boolean;
  onClose: () => void;
}

const NAV: { key: PageKey; label: string; icon: LucideIcon }[] = [
  { key: "overview", label: "Resumen", icon: LayoutDashboard },
  { key: "activity", label: "Actividad", icon: Activity },
  { key: "graph", label: "Grafo", icon: Workflow },
  { key: "findings", label: "Hallazgos", icon: ShieldCheck },
  { key: "settings", label: "Ajustes", icon: Settings },
];

/**
 * Barra lateral: marca, navegación real y selector de repositorio.
 *
 * En desktop (lg+) es fija y siempre visible. En móvil/tablet actúa como
 * panel "off-canvas": se desliza desde la izquierda controlada por `open`,
 * con una capa oscura de fondo que la cierra al hacer clic fuera.
 */
export function Sidebar({
  page,
  onNavigate,
  repos,
  selectedRepo,
  onSelectRepo,
  open,
  onClose,
}: SidebarProps) {
  const handleNavigate = (key: PageKey) => {
    onNavigate(key);
    onClose();
  };
  const handleSelectRepo = (repo: string) => {
    onSelectRepo(repo);
    onClose();
  };

  const { runs } = useStore();
  const { user, logout } = useAuth();
  const summaries = useMemo(() => repoHealthSummaries(runs, repos), [runs, repos]);
  const summaryByRepo = useMemo(() => new Map(summaries.map((s) => [s.repo, s])), [summaries]);

  return (
    <>
      {/* Overlay: solo visible en móvil/tablet cuando el menú está abierto. */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-border bg-surface transition-transform duration-200 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-3 px-5 py-5">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Arcus"
              className="h-8 w-8 rounded-md object-contain dark:brightness-0 dark:invert"
            />
            <div>
              <div className="text-base font-extrabold leading-none tracking-tight text-ink">Arcus</div>
              <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-muted">
                Repo Health
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="focus-ring grid h-8 w-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink lg:hidden"
            aria-label="Cerrar menú"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="mt-2 space-y-1 px-3">
          {NAV.map((item) => {
            const active = page === item.key;
            return (
              <button
                key={item.key}
                onClick={() => handleNavigate(item.key)}
                className={`focus-ring flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-surface-2 font-semibold text-ink"
                    : "text-muted hover:bg-surface-2 hover:text-ink"
                }`}
              >
                <item.icon size={17} strokeWidth={2} className={active ? "text-accent" : ""} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="mt-6 min-h-0 flex-1 overflow-y-auto px-3">
          <div className="flex items-center gap-2 px-2 pb-2 text-[0.68rem] font-semibold uppercase tracking-wider text-faint">
            <FolderGit2 size={13} />
            Repositorios
          </div>
          <div className="space-y-0.5">
            {repos.map((repo) => {
              const name = repo.split("/")[1] ?? repo;
              return (
                <RepoPreviewCard
                  key={repo}
                  name={name}
                  summary={summaryByRepo.get(repo)}
                  active={repo === selectedRepo}
                  onClick={() => handleSelectRepo(repo)}
                />
              );
            })}
          </div>
        </div>

        {user && (
          <div className="flex items-center justify-between gap-2 border-t border-border px-5 py-3">
            <span className="min-w-0 truncate text-xs font-medium text-ink">{user.login}</span>
            <button
              onClick={() => void logout()}
              className="focus-ring grid h-7 w-7 shrink-0 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-ink"
              aria-label="Cerrar sesión"
              title="Cerrar sesión"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}

        <div className="px-5 py-4 text-[0.68rem] text-faint">
          Arcus · Multiagente PR Review
          <br />
          Powered by Amazon Bedrock
        </div>
      </aside>
    </>
  );
}
