import { lazy, Suspense, useState } from "react";
import { Menu, RefreshCw, TriangleAlert } from "lucide-react";

import { Sidebar, type PageKey } from "@/components/Sidebar";
import { PageSkeleton } from "@/components/PageSkeleton";

import { ThemeProvider } from "@/state/ThemeProvider";
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
        ) : repos.length === 0 ? (
          <div className="panel p-6 text-sm text-muted">
            Todavía no hay revisiones registradas. En cuanto el pipeline procese un PR de
            GitHub, aparecerán aquí.
          </div>
        ) : (
          <div key={page} className="animate-fade-in">
            <Suspense fallback={<PageSkeleton />}>
              {page === "overview" && <OverviewPage />}
              {page === "activity" && <ActivityPage />}
              {page === "graph" && <GraphPage />}
              {page === "findings" && <FindingsPage />}
              {page === "settings" && <SettingsPage />}
            </Suspense>
          </div>
        )}

        <footer className="mt-8 flex flex-col items-start gap-1 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <span>Datos en vivo desde DynamoDB / S3</span>
          <span>Arcus · Repo Health Dashboard</span>
        </footer>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <StoreProvider>
        <Shell />
      </StoreProvider>
    </ThemeProvider>
  );
}
