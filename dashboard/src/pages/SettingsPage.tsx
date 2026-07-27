import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { ThemePreviewCard } from "@/components/ui/ThemePreview";
import { useStore } from "@/state/StoreProvider";
import { useTheme } from "@/state/ThemeProvider";
import type { ThemeMode } from "@/lib/theme";

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "Claro" },
  { value: "dark", label: "Oscuro" },
  { value: "system", label: "Sistema" },
];

/** Pantalla de ajustes: apariencia y configuración del backend (solo lectura). */
export function SettingsPage() {
  const { mode, setMode } = useTheme();
  const { repos, settings, selectedRepo, refresh } = useStore();
  const [refreshed, setRefreshed] = useState(false);

  return (
    <>
      <Header repo={selectedRepo} title="Ajustes" subtitle="Configura la apariencia del panel" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Apariencia */}
        <Panel title="Apariencia" subtitle="Tema de la interfaz">
          <span className="mb-1.5 block text-xs font-semibold text-muted">Tema</span>
          <div className="grid grid-cols-3 gap-2.5">
            {THEME_OPTIONS.map((o) => (
              <ThemePreviewCard
                key={o.value}
                mode={o.value}
                label={o.label}
                active={mode === o.value}
                onClick={() => setMode(o.value)}
              />
            ))}
          </div>
          <p className="mt-3 text-[0.8rem] text-muted">
            El tema se guarda en tu navegador y se aplica al recargar.
          </p>
        </Panel>

        {/* Backend */}
        <Panel title="Backend" subtitle="Configuración del pipeline desplegado">
          <div className="space-y-4">
            <div>
              <div className="mb-1 text-sm font-semibold text-ink">Región AWS</div>
              <input
                className="input cursor-not-allowed opacity-75"
                value={settings.region}
                readOnly
                aria-readonly="true"
              />
            </div>
            <div>
              <div className="mb-1 text-sm font-semibold text-ink">Modelo (Bedrock)</div>
              <input
                className="input cursor-not-allowed font-mono text-xs opacity-75"
                value={settings.modelId}
                readOnly
                aria-readonly="true"
              />
            </div>
            <p className="text-[0.72rem] text-faint">
              Estos valores son informativos; la configuración real vive en las variables de
              entorno del backend desplegado (BEDROCK_MODEL_ID, AWS_REGION).
            </p>
          </div>
        </Panel>

        {/* Repositorios (solo lectura: derivados de DynamoDB) */}
        <Panel title="Repositorios" subtitle="Repos con historial en DynamoDB">
          <div className="space-y-1.5">
            {repos.length === 0 ? (
              <p className="text-sm text-muted">Aún no hay repositorios con revisiones.</p>
            ) : (
              repos.map((repo) => (
                <div
                  key={repo}
                  className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2"
                >
                  <span className="font-mono text-sm text-ink">{repo}</span>
                </div>
              ))
            )}
          </div>
          <p className="mt-3 text-[0.72rem] text-faint">
            Esta lista se deriva de las revisiones que el pipeline ya procesó; los repos se
            agregan automáticamente al abrir un PR en un repositorio con la GitHub App
            instalada.
          </p>
        </Panel>

        {/* Datos */}
        <Panel title="Datos" subtitle="Sincronización con el backend">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              Los datos se leen en vivo de DynamoDB y S3 a través de la API del dashboard.
            </p>
            <button
              onClick={() => {
                refresh();
                setRefreshed(true);
                setTimeout(() => setRefreshed(false), 1500);
              }}
              className="btn-primary"
            >
              <RefreshCw size={14} />
              {refreshed ? "Actualizado" : "Actualizar ahora"}
            </button>
          </div>
        </Panel>
      </div>
    </>
  );
}
