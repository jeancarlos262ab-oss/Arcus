import { useState, type FormEvent } from "react";
import { ExternalLink, Plus, X } from "lucide-react";

import { Modal } from "@/components/Modal";
import { useStore } from "@/state/StoreProvider";
import { RUNTIME_CONFIG } from "@/lib/runtimeConfig";

interface ConnectRepoModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Ventana emergente para conectar un repositorio: enlaza a la instalación
 * real de la GitHub App (consentimiento del dueño en GitHub) y, por separado,
 * permite agregar un nombre a la watchlist local para tenerlo listo en el
 * selector antes de su primera revisión real.
 */
export function ConnectRepoModal({ open, onClose }: ConnectRepoModalProps) {
  const { addRepo, watchedRepos, removeRepo, disconnectAll } = useStore();
  const [newRepo, setNewRepo] = useState("");
  const [repoError, setRepoError] = useState<string | null>(null);

  const handleAddRepo = (e: FormEvent) => {
    e.preventDefault();
    const result = addRepo(newRepo);
    if (result.ok) {
      setNewRepo("");
      setRepoError(null);
    } else {
      setRepoError(result.error ?? "No se pudo agregar el repositorio.");
    }
  };

  const handleInstallOnGitHub = () => {
    if (!RUNTIME_CONFIG.githubAppInstallUrl) return;
    window.open(RUNTIME_CONFIG.githubAppInstallUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Conectar un repositorio"
      subtitle="Requiere autorización del dueño en GitHub"
    >
      <ol className="mb-4 space-y-2 text-sm text-muted">
        <li className="flex gap-2">
          <span className="font-semibold text-ink">1.</span>
          Haz clic en "Instalar Arcus en GitHub" y elige el repositorio (necesitas permisos
          de administrador sobre él).
        </li>
        <li className="flex gap-2">
          <span className="font-semibold text-ink">2.</span>
          Confirma los permisos que pide GitHub (lectura de contenido y PRs, comentarios).
        </li>
        <li className="flex gap-2">
          <span className="font-semibold text-ink">3.</span>
          Abre o actualiza un Pull Request en ese repositorio.
        </li>
        <li className="flex gap-2">
          <span className="font-semibold text-ink">4.</span>
          El pipeline lo procesa solo; en unos minutos aparece en el dashboard.
        </li>
      </ol>
      <button
        onClick={handleInstallOnGitHub}
        disabled={!RUNTIME_CONFIG.githubAppInstallUrl}
        className="btn-primary mb-4 w-full justify-center disabled:cursor-not-allowed disabled:opacity-50"
      >
        <ExternalLink size={14} />
        Instalar Arcus en GitHub
      </button>
      {!RUNTIME_CONFIG.githubAppInstallUrl && (
        <p className="-mt-3 mb-4 text-[0.72rem] text-faint">
          Falta configurar <code>VITE_GITHUB_APP_SLUG</code> en el dashboard para habilitar
          este enlace.
        </p>
      )}

      <div className="my-4 h-px bg-border" />

      <p className="mb-2 text-xs font-semibold text-muted">
        Agregar a la lista local (mientras no tenga revisiones)
      </p>
      <form onSubmit={handleAddRepo} className="mb-2 flex gap-2">
        <input
          className="input flex-1"
          placeholder="owner/repo"
          value={newRepo}
          onChange={(e) => {
            setNewRepo(e.target.value);
            setRepoError(null);
          }}
        />
        <button type="submit" className="btn-primary shrink-0">
          <Plus size={14} />
          Agregar
        </button>
      </form>
      {repoError && <p className="mb-2 text-xs text-red-500">{repoError}</p>}

      {watchedRepos.length > 0 && (
        <div className="space-y-1.5">
          {watchedRepos.map((repo) => (
            <div
              key={repo}
              className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2"
            >
              <span className="font-mono text-sm text-ink">{repo}</span>
              <button
                onClick={() => removeRepo(repo)}
                className="focus-ring grid h-6 w-6 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-ink"
                aria-label={`Quitar ${repo} de la lista`}
                title="Quitar de la lista"
              >
                <X size={13} />
              </button>
            </div>
          ))}
          <button
            onClick={disconnectAll}
            className="mt-1 text-[0.72rem] text-faint underline-offset-2 hover:text-ink hover:underline"
          >
            Desconectar todo
          </button>
        </div>
      )}

      <p className="mt-3 text-[0.72rem] text-faint">
        Este campo solo agrega el nombre a tu lista local del navegador; no instala nada en
        GitHub. Los repos con revisiones reales aparecen automáticamente en cuanto el pipeline
        procese su primer PR.
      </p>
    </Modal>
  );
}
