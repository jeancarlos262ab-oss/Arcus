import { useState } from "react";

import { Sidebar, type PageKey } from "@/components/Sidebar";
import { OverviewPage } from "@/pages/OverviewPage";
import { ActivityPage } from "@/pages/ActivityPage";
import { GraphPage } from "@/pages/GraphPage";
import { FindingsPage } from "@/pages/FindingsPage";
import { SettingsPage } from "@/pages/SettingsPage";

import { ThemeProvider } from "@/state/ThemeProvider";
import { StoreProvider, useStore } from "@/state/StoreProvider";

function Shell() {
  const { repos, selectedRepo, setSelectedRepo } = useStore();
  const [page, setPage] = useState<PageKey>("overview");

  return (
    <div className="min-h-screen">
      <Sidebar
        page={page}
        onNavigate={setPage}
        repos={repos}
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
      />

      <main className="ml-64 px-8 py-7">
        <div key={page} className="animate-fade-in">
          {page === "overview" && <OverviewPage onNewReview={() => setPage("activity")} />}
          {page === "activity" && <ActivityPage />}
          {page === "graph" && <GraphPage />}
          {page === "findings" && <FindingsPage />}
          {page === "settings" && <SettingsPage />}
        </div>

        <footer className="mt-8 flex items-center justify-between text-xs text-faint">
          <span>Datos simulados · listo para conectar API de DynamoDB</span>
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
