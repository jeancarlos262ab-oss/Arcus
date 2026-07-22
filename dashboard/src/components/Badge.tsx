import type { AgentStatus, Severity } from "@/lib/types";
import { alpha, severityColor, statusColor, SEVERITY_LABEL, STATUS_LABEL } from "@/lib/theme";
import { useTheme } from "@/state/ThemeProvider";

function Dot({ color }: { color: string }) {
  return <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { p } = useTheme();
  const color = severityColor(p, severity);
  return (
    <span className="chip" style={{ background: alpha(color, 0.14), color }}>
      <Dot color={color} />
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

export function StatusBadge({ status }: { status: AgentStatus }) {
  const { p } = useTheme();
  const color = statusColor(p, status);
  return (
    <span className="chip" style={{ background: alpha(color, 0.14), color }}>
      <Dot color={color} />
      {STATUS_LABEL[status]}
    </span>
  );
}

/** Chip genérico; si recibe `color` lo tiñe, si no usa el neutro. */
export function Chip({ children, color }: { children: React.ReactNode; color?: string }) {
  if (color) {
    return (
      <span className="chip" style={{ background: alpha(color, 0.14), color }}>
        {children}
      </span>
    );
  }
  return <span className="chip bg-surface-2 text-muted">{children}</span>;
}
