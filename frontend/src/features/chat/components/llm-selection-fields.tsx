import { BrainCircuit, Cpu, Layers } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export const llmProviders = ["openai", "ollama"] as const;
export const reasoningEfforts = ["low", "medium", "high"] as const;

export type LLMProvider = (typeof llmProviders)[number];
export type ReasoningEffort = (typeof reasoningEfforts)[number];

interface LLMSelectionFieldsProps {
  provider: string;
  onProviderChange: (value: LLMProvider | "") => void;
  model: string;
  onModelChange: (value: string) => void;
  reasoningCheck?: boolean;
  onReasoningCheckChange?: (value: boolean) => void;
  reasoningEffort?: ReasoningEffort;
  onReasoningEffortChange?: (value: ReasoningEffort) => void;
  disabled?: boolean;
  className?: string;
  compact?: boolean;
}

const inputClassName =
  "h-10 w-full rounded-2xl border border-border/60 bg-background/70 px-4 py-2 text-sm font-medium text-foreground shadow-inner focus-visible:ring-1 focus-visible:ring-primary/60";
const selectTriggerClassName =
  "h-10 w-full rounded-2xl border border-border/60 bg-background/70 px-4 text-sm font-medium text-foreground shadow-inner focus:outline-none focus:ring-1 focus:ring-primary/60";
const selectContentClassName =
  "rounded-xl border border-white/10 bg-black/90 text-zinc-100 shadow-2xl shadow-indigo-500/20 backdrop-blur";

export function LLMSelectionFields({
  provider,
  onProviderChange,
  model,
  onModelChange,
  reasoningCheck,
  onReasoningCheckChange,
  reasoningEffort,
  onReasoningEffortChange,
  disabled,
  className,
  compact = false
}: LLMSelectionFieldsProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      <div className="flex w-full items-center gap-2 sm:w-auto">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground shrink-0">
          <Cpu size={16} />
        </div>
        <div className="relative min-w-[160px]">
          <Select
            value={provider || "default"}
            onValueChange={(val) => onProviderChange(val === "default" ? "" : (val as LLMProvider))}
            disabled={disabled}
          >
            <SelectTrigger className={selectTriggerClassName}>
              <SelectValue placeholder="Default provider" />
            </SelectTrigger>
            <SelectContent className={selectContentClassName}>
              <SelectItem value="default">Default provider</SelectItem>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="ollama">Ollama</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {provider === "ollama" && onReasoningCheckChange && (
        <div className="flex w-full items-center gap-4 sm:w-auto">
          <div className="flex items-center gap-2">
            <Checkbox
              id="reasoning-check"
              checked={reasoningCheck}
              onCheckedChange={(checked) => onReasoningCheckChange(!!checked)}
              disabled={disabled}
              className="h-5 w-5 rounded-md"
            />
            <Label
              htmlFor="reasoning-check"
              className="flex items-center gap-1.5 text-sm font-medium text-foreground cursor-pointer whitespace-nowrap"
            >
              <BrainCircuit size={14} className="text-primary" />
              Reasoning
            </Label>
          </div>
          {reasoningCheck && onReasoningEffortChange && (
            <div className="flex items-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground shrink-0">
                <Layers size={16} />
              </div>
              <div className="relative min-w-[130px]">
                <Select
                  value={reasoningEffort || "high"}
                  onValueChange={(val) => onReasoningEffortChange(val as ReasoningEffort)}
                  disabled={disabled}
                >
                  <SelectTrigger className={selectTriggerClassName}>
                    <SelectValue placeholder="Select effort" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    <SelectItem value="low">Low effort</SelectItem>
                    <SelectItem value="medium">Medium effort</SelectItem>
                    <SelectItem value="high">High effort</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>
      )}

      <div className={cn("flex w-full items-center gap-2 sm:min-w-[200px]", !compact && "sm:flex-1")}>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground shrink-0">
          <Layers size={16} />
        </div>
        <Input
          aria-label="Model"
          placeholder={model || (provider === "ollama" ? "devstral-small-2:24b" : "gpt-4o")}
          className={inputClassName}
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
