import { Gauge, Zap } from "lucide-react";
import { PreviewCard } from "./PreviewCard";

export interface ModelOption {
  modelId: string;
  name: string;
  /** 1-3: relativo entre las opciones, no un valor absoluto real. */
  speed: number;
  cost: number;
}

/** Modelos de Claude vía Bedrock disponibles para el pipeline de agentes. */
export const MODEL_OPTIONS: ModelOption[] = [
  {
    modelId: "anthropic.claude-3-5-haiku-20241022-v1:0",
    name: "Haiku 3.5",
    speed: 3,
    cost: 1,
  },
  {
    modelId: "anthropic.claude-3-5-sonnet-20240620-v1:0",
    name: "Sonnet 3.5",
    speed: 2,
    cost: 2,
  },
  {
    modelId: "anthropic.claude-3-opus-20240229-v1:0",
    name: "Opus 3",
    speed: 1,
    cost: 3,
  },
];

/** Barra de 3 segmentos que representa un nivel relativo (velocidad/costo). */
function LevelBar({ level, color }: { level: number; color: string }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className="h-1.5 w-3.5 rounded-full"
          style={{ background: i <= level ? color : "var(--border)" }}
        />
      ))}
    </div>
  );
}

/** Mini-mockup: nombre del modelo + barras relativas de velocidad y costo. */
function MiniModelMockup({ option }: { option: ModelOption }) {
  return (
    <div className="rounded-md border border-border bg-bg p-2">
      <div className="text-[0.7rem] font-bold text-ink">{option.name}</div>
      <div className="mt-1.5 space-y-1">
        <div className="flex items-center gap-1.5">
          <Zap size={10} className="shrink-0 text-faint" />
          <LevelBar level={option.speed} color="#8B5CF6" />
        </div>
        <div className="flex items-center gap-1.5">
          <Gauge size={10} className="shrink-0 text-faint" />
          <LevelBar level={option.cost} color="#F59E0B" />
        </div>
      </div>
    </div>
  );
}

interface ModelPreviewCardProps {
  option: ModelOption;
  active: boolean;
  onClick: () => void;
}

/** Tarjeta de opción de modelo Bedrock con velocidad/costo relativos visualizados. */
export function ModelPreviewCard({ option, active, onClick }: ModelPreviewCardProps) {
  return (
    <PreviewCard
      active={active}
      onClick={onClick}
      label={option.name}
      preview={<MiniModelMockup option={option} />}
    />
  );
}
