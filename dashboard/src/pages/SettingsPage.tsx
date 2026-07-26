import { useState } from "react";
import { Check, Monitor, Moon, Plus, Sun, Trash2, TriangleAlert } from "lucide-react";

import { Header } from "@/components/Header";
import { Panel } from "@/components/Panel";
import { Field, Segmented, Select, Toggle } from "@/components/ui/Field";
import { useStore } from "@/state/StoreProvider";
import { useTheme } from "@/state/ThemeProvider";
import type { ThemeMode } from "@/lib/theme";
import type { Severity } from "@/lib/types";

/** Pantalla de ajustes: apariencia, repos, pipeline, integración y datos. */
export function SettingsPage() {
  const { mode, setMode } = useTheme();
  const { repos, settings, selectedRepo, addRepo, removeRepo, updateSettings, resetData } =
    useStore();

  const [newRepo, setNewRepo] = useState("");
  const [repoError, setRepoError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const onAddRepo = () => {
    const res = addRepo(newRepo);
    if (res.ok) {
      setNewRepo("");
      setRepoError(null);
    } else {
      setRepoError(res.error ?? "No se pudo agregar.");
    }
  };

  return (
    <>
      <Header repo={selectedRepo} title="Ajustes" subtitle="Configura Arcus y la apariencia del panel" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Apariencia */}
        <Panel title="Apariencia" subtitle="Tema de la interfaz">
          <Field label="Tema">
            <Segmented<ThemeMode>
              value={mode}
              onChange={setMode}
              options={[
                { value: "light", label: "Claro", icon: <Sun size={14} /> },
                { value: "dark", label: "Oscuro", icon: <Moon size={14} /> },
                { value: "system", label: "Sistema", icon: <Monitor size={14} /> },
              ]}
            />
          </Field>
          <p className="mt-3 text-[0.8rem] text-muted">
            El tema se guarda en tu navegador y se aplica al recargar.
          </p>
        </Panel>

        {/* Pipeline */}
        <Panel title="Pipeline" subtitle="Comportamiento de la revisión">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-ink">Comentar automáticamente</div>
                <div className="text-[0.78rem] text-muted">Publica el hallazgo como comentario en el PR</div>
              </div>
              <Toggle
                checked={settings.autoComment}
                onChange={(v) => updateSettings({ autoComment: v })}
              />
            </div>
            <Field label="Severidad mínima para comentar">
              <Select<Severity>
                value={settings.minSeverityToComment}
                onChange={(v) => updateSettings({ minSeverityToComment: v })}
                options={[
                  { value: "low", label: "Baja o superior" },
                  { value: "medium", label: "Media o superior" },
                  { value: "high", label: "Solo alta" },
                ]}
              />
            </Field>
            <Field
              label="Región AWS"
              hint="La región de ejecución la controla el backend desplegado."
            >
              <input
                className="input cursor-not-allowed opacity-75"
                value={settings.region}
                readOnly
                aria-readonly="true"
              />
            </Field>
            <Field
              label="Modelo (Bedrock)"
              hint="El modelo se configura en Lambda mediante BEDROCK_MODEL_ID."
            >
              <input
                className="input cursor-not-allowed font-mono text-xs opacity-75"
                value={settings.modelId}
                readOnly
                aria-readonly="true"
              />
            </Field>
            <p className="text-[0.78rem] text-muted">
              Estos valores son informativos y no se guardan como configuración de ejecución en
              el navegador.
            </p>
          </div>
        </Panel>

        {/* Repositorios */}
        <Panel title="Repositorios" subtitle="Repos monitoreados por Arcus">
          <div className="flex gap-2">
            <input
              className="input"
              placeholder="owner/repo"
              value={newRepo}
              onChange={(e) => {
                setNewRepo(e.target.value);
                setRepoError(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && onAddRepo()}
            />
            <button onClick={onAddRepo} className="btn-primary shrink-0">
              <Plus size={16} />
              Agregar
            </button>
          </div>
          {repoError && <p className="mt-1.5 text-xs text-high">{repoError}</p>}

          <div className="mt-3 space-y-1.5">
            {repos.map((repo) => (
              <div
                key={repo}
                className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2"
              >
                <span className="font-mono text-sm text-ink">{repo}</span>
                <button
                  onClick={() => removeRepo(repo)}
                  disabled={repos.length <= 1}
                  className="focus-ring rounded-md p-1 text-faint transition-colors hover:text-high disabled:opacity-40"
                  title={repos.length <= 1 ? "Debe quedar al menos un repo" : "Eliminar"}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </Panel>

        {/* Integración GitHub */}
        <Panel title="Integración GitHub" subtitle="Credenciales de la GitHub App">
          <div className="space-y-4">
            <Field
              label="GitHub App ID"
              hint="Se obtiene al registrar la App en GitHub y lo informa el backend."
            >
              <input
                className="input cursor-not-allowed opacity-75"
                placeholder="Configurado en el backend"
                value={settings.githubAppId}
                readOnly
                aria-readonly="true"
              />
            </Field>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-ink">Webhook configurado</div>
                <div className="text-[0.78rem] text-muted">Firma HMAC verificada por el backend</div>
              </div>
              <Toggle checked={settings.webhookConfigured} disabled />
            </div>
            <div
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
                settings.githubAppId && settings.webhookConfigured
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-medium/30 bg-medium/10 text-medium"
              }`}
            >
              {settings.githubAppId && settings.webhookConfigured ? (
                <>
                  <Check size={14} /> Integración lista
                </>
              ) : (
                <>
                  <TriangleAlert size={14} /> Configura la GitHub App y el webhook en AWS
                </>
              )}
            </div>
          </div>
        </Panel>
      </div>

      {/* Zona de peligro */}
      <Panel title="Datos" subtitle="Gestión del estado local" className="mt-4 border-high/30">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">
            Restablece los datos simulados a su estado inicial. Se borran las revisiones que hayas
            ejecutado en esta sesión.
          </p>
          {confirmReset ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">¿Seguro?</span>
              <button
                onClick={() => {
                  resetData();
                  setConfirmReset(false);
                }}
                className="btn bg-high text-white hover:opacity-90"
              >
                Sí, restablecer
              </button>
              <button onClick={() => setConfirmReset(false)} className="btn-ghost">
                Cancelar
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirmReset(true)} className="btn-ghost text-high">
              <Trash2 size={16} />
              Restablecer datos
            </button>
          )}
        </div>
      </Panel>
    </>
  );
}
