import { useEffect, useState, type FormEvent } from "react";
import { ExternalLink, Plus, X } from "lucide-react";

import { Modal } from "@/components/Modal";
import { useStore } from "@/state/StoreProvider";
import { fetchMyRepos } from "@/lib/authApi";
import { RUNTIME_CONFIG } from "@/lib/runtimeConfig";

interface ConnectRepoModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Ventana emergente para conectar un repositorio: enlaza a la instalación
 * real de la GitHub App (consentimiento del dueño en GitHub) y, por separado,
 * permite elegir cuáles de tus propios repos de GitHub ver en el dashboard.
 * La selección se guarda en tu cuenta, no en este navegador.
 */
export function ConnectRepoModal({ open, onClose }: ConnectRepoModalProps) {
  const { addRepo, watchedRepos, removeRepo, disconnectAll, availableRepos } = useStore();
  const [newRepo, setNewRepo] = useState("");
  const [repoError, setRepoError] = useState<string | null>(null);
  const [myRepos, setMyRepos] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetchMyRepos()
      .then((repos) => {
        if (!cancelled) setMyRepos(repos.map((r) => r.full_name));
      })
      .catch(() => {
        // Silencioso: la lista de sugerencias es una comodidad, no algo crítico.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleAddRepo = async (e: FormEvent) => {
    e.preventDefault();
    const result = await addRepo(newRepo);
    if (result.ok) {
      setNewRepo("");
      setRepoError(null);
    } else {
      setRepoError(result.error ?? "No se pudo agregar el repositorio.");
    }
  };

  const suggestions = [...new Set([...myRepos, ...availableRepos])].filter(
    (repo) => !watchedRepos.includes(repo),
  );

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

      <p className="mb-2 text-xs font-semibold text-muted">Elegir un repositorio para tu cuenta</p>
      <form onSubmit={(e) => void handleAddRepo(e)} className="mb-2 flex gap-2">
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

      {suggestions.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[0.72rem] text-faint">Tus repositorios de GitHub:</p>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((repo) => (
              <button
                key={repo}
                onClick={() => void addRepo(repo)}
                className="focus-ring rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-ink"
              >
                {repo}
              </button>
            ))}
          </div>
        </div>
      )}

      {watchedRepos.length > 0 && (
        <div className="space-y-1.5">
          <p className="mb-1.5 text-[0.72rem] text-faint">Tu lista actual:</p>
          {watchedRepos.map((repo) => (
            <div
              key={repo}
              className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2"
            >
              <span className="font-mono text-sm text-ink">{repo}</span>
              <button
                onClick={() => void removeRepo(repo)}
                className="focus-ring grid h-6 w-6 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-ink"
                aria-label={`Quitar ${repo} de tu lista`}
                title="Quitar de tu lista"
              >
                <X size={13} />
              </button>
            </div>
          ))}
          <button
            onClick={() => void disconnectAll()}
            className="mt-1 text-[0.72rem] text-faint underline-offset-2 hover:text-ink hover:underline"
          >
            Quitar todos
          </button>
        </div>
      )}

      <p className="mt-3 text-[0.72rem] text-faint">
        Esta lista es solo tuya, guardada en tu cuenta; no afecta lo que ven otras personas ni
        instala nada en GitHub. El repositorio debe tener la GitHub App instalada y al menos
        un Pull Request procesado para mostrar datos.
      </p>
    </Modal>
  );
}
