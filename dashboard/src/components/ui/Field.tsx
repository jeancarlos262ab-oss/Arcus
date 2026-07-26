import type { ReactNode } from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";

/** Etiqueta + control de formulario con descripción opcional. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[0.72rem] text-faint">{hint}</span>}
    </label>
  );
}

interface SelectProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
}

/** Select estilizado y controlado. */
export function Select<T extends string>({ value, onChange, options }: SelectProps<T>) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="input cursor-pointer appearance-none pr-8"
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238B949E' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 0.6rem center",
      }}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/**
 * Interruptor on/off accesible, sobre Radix UI (`@radix-ui/react-switch`).
 *
 * Radix maneja el estado, el teclado y el foco de forma nativa; el thumb usa
 * `translate-x-full` dentro de un track de ancho fijo para que nunca se
 * salga del contenedor, sin importar el tema.
 */
export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange?: (v: boolean) => void;
  label?: string;
  /** Bloquea la interacción cuando el valor lo controla el backend, no el navegador. */
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2.5 ${disabled ? "cursor-not-allowed opacity-75" : ""}`}
    >
      <SwitchPrimitive.Root
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        className="focus-ring relative h-5 w-9 shrink-0 rounded-full bg-border-strong outline-none transition-colors data-[state=checked]:bg-accent data-[disabled]:cursor-not-allowed"
      >
        <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform duration-150 will-change-transform data-[state=checked]:translate-x-[18px]" />
      </SwitchPrimitive.Root>
      {label && <span className="text-sm text-ink">{label}</span>}
    </label>
  );
}

/** Control segmentado (para elegir entre pocas opciones). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; icon?: ReactNode }[];
}) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-surface p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`focus-ring flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
            value === o.value ? "bg-accent text-bg" : "text-muted hover:text-ink"
          }`}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}
