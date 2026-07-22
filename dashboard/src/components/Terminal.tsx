import { useEffect, useRef } from "react";
import { Circle, TerminalSquare } from "lucide-react";
import type { LogLine, LogLevel } from "@/lib/simulate";

interface TerminalProps {
  lines: LogLine[];
  running: boolean;
  title?: string;
}

const LEVEL_CLASS: Record<LogLevel, string> = {
  info: "text-muted",
  success: "text-success",
  warn: "text-medium",
  error: "text-high",
};

/** Consola que muestra el stream de logs del pipeline en vivo. */
export function Terminal({ lines, running, title = "pipeline · ejecución en vivo" }: TerminalProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines.length]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-bg">
      {/* Barra de título estilo terminal */}
      <div className="flex items-center gap-2 border-b border-border bg-surface px-3.5 py-2.5">
        <div className="flex gap-1.5">
          <Circle size={10} className="fill-high text-high" />
          <Circle size={10} className="fill-medium text-medium" />
          <Circle size={10} className="fill-success text-success" />
        </div>
        <div className="ml-2 flex items-center gap-1.5 text-xs font-medium text-muted">
          <TerminalSquare size={13} />
          {title}
        </div>
        {running && (
          <span className="ml-auto flex items-center gap-1.5 text-[0.7rem] font-semibold text-accent">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            corriendo
          </span>
        )}
      </div>

      {/* Cuerpo */}
      <div className="h-[340px] overflow-y-auto p-3.5 font-mono text-[0.78rem] leading-relaxed">
        {lines.length === 0 ? (
          <p className="text-faint">
            $ Esperando ejecución… pulsa <span className="text-accent">Ejecutar revisión</span>.
          </p>
        ) : (
          lines.map((l) => (
            <div key={l.id} className="flex gap-2">
              <span className="shrink-0 text-faint">{l.ts}</span>
              <span className="shrink-0 text-accent">{l.agent}</span>
              <span className={LEVEL_CLASS[l.level]}>{l.message}</span>
            </div>
          ))
        )}
        {running && <span className="inline-block h-3.5 w-2 animate-pulse bg-accent align-middle" />}
        <div ref={endRef} />
      </div>
    </div>
  );
}
