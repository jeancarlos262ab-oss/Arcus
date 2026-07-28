import { lazy, Suspense, useState, type ReactNode } from "react";
import { Github, Menu, Plug, RefreshCw, TriangleAlert } from "lucide-react";

import { Sidebar, type PageKey } from "@/components/Sidebar";
import { PageSkeleton } from "@/components/PageSkeleton";
import { ConnectRepoModal } from "@/components/ConnectRepoModal";

import { ThemeProvider } from "@/state/ThemeProvider";
import { AuthProvider, useAuth } from "@/state/AuthProvider";
import { StoreProvider, useStore } from "@/state/StoreProvider";

// Carga diferida por página: cada pantalla (y sus dependencias pesadas, como
// Recharts o react-force-graph-2d) se descarga solo cuando el usuario navega
// a ella, en vez de ir toda en el bundle inicial.
const OverviewPage = lazy(() =>
  import("@/pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const ActivityPage = lazy(() =>
  import("@/pages/ActivityPage").then((m) => ({ default: m.ActivityPage })),
);
const GraphPage = lazy(() => import("@/pages/GraphPage").then((m) => ({ default: m.GraphPage })));
const FindingsPage = lazy(() =>
  import("@/pages/FindingsPage").then((m) => ({ default: m.FindingsPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);

function Shell() {
  const { loading, error, repos, selectedRepo, setSelectedRepo, refresh } = useStore();
  const [page, setPage] = useState<PageKey>("overview");
  // El menú lateral es "off-canvas" por debajo del breakpoint `lg`: se abre/
  // cierra con este estado. En `lg+` el sidebar ignora `open` y siempre se ve.
  const [menuOpen, setMenuOpen] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <Sidebar
        page={page}
        onNavigate={setPage}
        repos={repos}
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <main className="px-4 py-5 sm:px-6 sm:py-6 lg:ml-56 lg:px-7 lg:py-6">
        {/* Botón para mostrar el menú, solo visible por debajo de `lg`. */}
        <button
          onClick={() => setMenuOpen(true)}
          className="focus-ring btn-ghost mb-4 lg:hidden"
          aria-label="Abrir menú"
        >
          <Menu size={16} />
          Menú
        </button>

        {error ? (
          <div className="panel flex flex-col items-start gap-3 p-6">
            <div className="flex items-center gap-2 text-high">
              <TriangleAlert size={18} />
              <span className="font-semibold">No se pudo conectar con la API de Arcus</span>
            </div>
            <p className="text-sm text-muted">{error}</p>
            <button onClick={refresh} className="btn-primary">
              <RefreshCw size={14} />
              Reintentar
            </button>
          </div>
        ) : loading ? (
          <PageSkeleton />
        ) : page === "settings" ? (
          // Ajustes siempre es accesible, incluso sin repos: ahí también se puede conectar uno.
          <div key={page} className="animate-fade-in">
            <Suspense fallback={<PageSkeleton />}>
              <SettingsPage />
            </Suspense>
          </div>
        ) : repos.length === 0 ? (
          <div className="panel flex flex-col items-start gap-4 p-6">
            <div>
              <p className="text-sm font-semibold text-ink">
                Todavía no hay repositorios conectados
              </p>
              <p className="mt-1 text-sm text-muted">
                Sigue estos pasos para empezar a ver revisiones reales:
              </p>
            </div>
            <ol className="w-full space-y-2 text-sm text-muted">
              <li className="flex gap-2">
                <span className="font-semibold text-ink">1.</span>
                Instala la GitHub App de Arcus en el repositorio (requiere tu autorización
                como dueño, directamente en GitHub).
              </li>
              <li className="flex gap-2">
                <span className="font-semibold text-ink">2.</span>
                Abre o actualiza un Pull Request en ese repositorio.
              </li>
              <li className="flex gap-2">
                <span className="font-semibold text-ink">3.</span>
                El pipeline lo procesa solo; en unos minutos aparece aquí.
              </li>
            </ol>
            <button onClick={() => setConnectOpen(true)} className="btn-primary">
              <Plug size={14} />
              Conectar un repositorio
            </button>
          </div>
        ) : (
          <div key={page} className="animate-fade-in">
            <Suspense fallback={<PageSkeleton />}>
              {page === "overview" && <OverviewPage />}
              {page === "activity" && <ActivityPage />}
              {page === "graph" && <GraphPage />}
              {page === "findings" && <FindingsPage />}
            </Suspense>
          </div>
        )}

        <footer className="mt-8 flex flex-col items-start gap-1 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <span>Datos en vivo desde DynamoDB / S3</span>
          <span>Arcus · Repo Health Dashboard</span>
        </footer>
      </main>

      <ConnectRepoModal open={connectOpen} onClose={() => setConnectOpen(false)} />
    </div>
  );
}

/**
 * Exige un login real de GitHub antes de mostrar cualquier dato. Cada
 * persona ve únicamente su propia sesión y su propia selección de repos;
 * nunca hay un usuario ni una lista compartida por defecto.
 */
function AuthGate({ children }: { children: ReactNode }) {
  const { loading, user, configError, login } = useAuth();

  if (configError) {
    return (
      <div className="grid min-h-screen place-items-center p-6">
        <div className="panel flex max-w-md flex-col items-start gap-3 p-6">
          <div className="flex items-center gap-2 text-high">
            <TriangleAlert size={18} />
            <span className="font-semibold">Dashboard no configurado</span>
          </div>
          <p className="text-sm text-muted">{configError}</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <PageSkeleton />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="grid min-h-screen place-items-center p-6">
        <div className="panel flex max-w-sm flex-col items-center gap-4 p-8 text-center">
          <img src="/logo.png" alt="Arcus" className="h-12 w-12 dark:brightness-0 dark:invert" />
          <div>
            <h1 className="text-lg font-extrabold text-ink">Arcus Repo Health</h1>
            <p className="mt-1 text-sm text-muted">
              Inicia sesión con GitHub para ver tus propios repositorios y sus revisiones.
            </p>
          </div>
          <button onClick={login} className="btn-primary w-full justify-center">
            <Github size={16} />
            Iniciar sesión con GitHub
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AuthGate>
          <StoreProvider>
            <Shell />
          </StoreProvider>
        </AuthGate>
      </AuthProvider>
    </ThemeProvider>
  );
}
