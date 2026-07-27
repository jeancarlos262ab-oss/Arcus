import { useEffect } from "react";
import { X } from "lucide-react";
import { createPortal } from "react-dom";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

/**
 * Ventana emergente genérica y accesible: overlay + cierre con Escape/click
 * fuera. Se usa para acciones puntuales (como conectar un repo) sin navegar
 * a otra pantalla.
 */
export function Modal({ open, onClose, title, subtitle, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="panel relative w-full max-w-md p-5 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink">{title}</h2>
            {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="focus-ring grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
