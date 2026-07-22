import { Activity, FolderGit2, LayoutDashboard, Settings, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type PageKey = "overview" | "activity" | "findings" | "settings";

interface SidebarProps {
  page: PageKey;
  onNavigate: (page: PageKey) => void;
  repos: string[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
}

const NAV: { key: PageKey; label: string; icon: LucideIcon }[] = [
  { key: "overview", label: "Resumen", icon: LayoutDashboard },
  { key: "activity", label: "Actividad", icon: Activity },
  { key: "findings", label: "Hallazgos", icon: ShieldCheck },
  { key: "settings", label: "Ajustes", icon: Settings },
];

/** Barra lateral: marca, navegación real y selector de repositorio. */
export function Sidebar({ page, onNavigate, repos, selectedRepo, onSelectRepo }: SidebarProps) {
  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-64 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="grid h-9 w-9 place-items-center rounded-[10px] bg-gradient-to-br from-accent to-accent-hover text-lg font-extrabold text-bg shadow-glow">
          A
        </div>
        <div>
          <div className="text-lg font-extrabold leading-none tracking-tight text-ink">Arcus</div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-muted">
            Repo Health
          </div>
        </div>
      </div>

      <nav className="mt-2 space-y-1 px-3">
        {NAV.map((item) => {
          const active = page === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
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
            const active = repo === selectedRepo;
            return (
              <button
                key={repo}
                onClick={() => onSelectRepo(repo)}
                className={`focus-ring flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  active
                    ? "bg-accent/10 font-semibold text-accent"
                    : "text-muted hover:bg-surface-2 hover:text-ink"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-accent" : "bg-faint"}`} />
                <span className="truncate">{name}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="px-5 py-4 text-[0.68rem] text-faint">
        Arcus · Multiagente PR Review
        <br />
        Powered by Amazon Bedrock
      </div>
    </aside>
  );
}
