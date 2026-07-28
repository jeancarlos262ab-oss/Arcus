import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, ExternalLink, Plus, X } from "lucide-react";

import { Modal } from "@/components/Modal";
import { useStore } from "@/state/StoreProvider";
import { fetchMyRepos, type MyRepo } from "@/lib/authApi";
import { RUNTIME_CONFIG } from "@/lib/runtimeConfig";

interface ConnectRepoModalProps {
  open: boolean;
  onClose: () => void;
}

function openInstallUrl() {
  if (!RUNTIME_CONFIG.githubAppInstallUrl) return;
  window.open(RUNTIME_CONFIG.githubAppInstallUrl, "_blank", "noopener,noreferrer");
}

/**
 * Ventana emergente para conectar un repositorio. Muestra los repos reales
 * del usuario logueado con su estado real de instalación de la GitHub App
 * (consultado a GitHub, no simulado): si ya está instalada, solo se puede
 * agregar a la selección; si falta, aparece un botón que lleva a la
 * instalación real en GitHub. La selección se guarda en la cuenta del
 * usuario, nunca en este navegador.
 */
export function ConnectRepoModal({ open, onClose }: ConnectRepoModalProps) {
  const { addRepo, watchedRepos, removeRepo, disconnectAll } = useStore();
  const [newRepo, setNewRepo] = useState("");
  const [repoError, setRepoError] = useState<string | null>(null);
  const [myRepos, setMyRepos] = useState<MyRepo[] | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setMyRepos(null);
    setReposError(null);
    fetchMyRepos()
      .then((repos) => {
        if (!cancelled) setMyRepos(repos);
      })
      .catch(() => {
        if (!cancelled) {
          setReposError("No se pudo cargar la lista de tus repositorios de GitHub.");
        }
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

  const suggestions = (myRepos ?? []).filter((repo) => !watchedRepos.includes(repo.full_name));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Conectar un repositorio"
      subtitle="Estado real de instalación de la GitHub App"
    >
      <p className="mb-3 text-sm text-muted">
        Estos son tus repositorios de GitHub. Los que ya tienen la App instalada solo
        necesitan agregarse a tu selección; los que no, primero requieren que instales la
        App (necesitas permisos de administrador sobre ese repo).
      </p>

      {reposError && <p className="mb-3 text-xs text-red-500">{reposError}</p>}

      {myRepos === null && !reposError ? (
        <p className="mb-3 text-sm text-muted">Cargando tus repositorios…</p>
      ) : suggestions.length === 0 ? (
        <p className="mb-3 text-sm text-muted">
          {watchedRepos.length > 0
            ? "Ya agregaste todos tus repositorios disponibles."
            : "No encontramos repositorios en tu cuenta de GitHub."}
        </p>
      ) : (
        <div className="mb-4 max-h-48 space-y-1.5 overflow-y-auto">
          {suggestions.map((repo) => (
            <div
              key={repo.full_name}
              className="flex items-center justify-between gap-2 rounded-lg border border-border bg-bg px-3 py-2"
            >
              <span className="min-w-0 truncate font-mono text-sm text-ink">
                {repo.full_name}
              </span>
              {repo.app_installed ? (
                <button
                  onClick={() => void addRepo(repo.full_name)}
                  className="btn-primary shrink-0 px-2.5 py-1 text-xs"
                >
                  <Plus size={12} />
                  Agregar
                </button>
              ) : (
                <button
                  onClick={openInstallUrl}
                  disabled={!RUNTIME_CONFIG.githubAppInstallUrl}
                  className="btn-ghost shrink-0 px-2.5 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                  title="Instalar Arcus en GitHub para este repositorio"
                >
                  <ExternalLink size={12} />
                  Instalar
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {!RUNTIME_CONFIG.githubAppInstallUrl && (
        <p className="-mt-2 mb-3 text-[0.72rem] text-faint">
          Falta configurar <code>VITE_GITHUB_APP_SLUG</code> en el dashboard para habilitar
          el botón "Instalar".
        </p>
      )}

      <div className="my-4 h-px bg-border" />

      <p className="mb-2 text-xs font-semibold text-muted">
        Agregar otro repositorio por nombre
      </p>
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

      {watchedRepos.length > 0 && (
        <div className="space-y-1.5">
          <p className="mb-1.5 text-[0.72rem] text-faint">Tu lista actual:</p>
          {watchedRepos.map((repo) => (
            <div
              key={repo}
              className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2"
            >
              <span className="flex items-center gap-1.5 font-mono text-sm text-ink">
                <CheckCircle2 size={13} className="shrink-0 text-accent" />
                {repo}
              </span>
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
        Esta lista es solo tuya, guardada en tu cuenta; no afecta lo que ven otras personas.
        Un repositorio necesita la GitHub App instalada y al menos un Pull Request procesado
        para mostrar datos.
      </p>
    </Modal>
  );
}
