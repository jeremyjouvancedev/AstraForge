import { useMemo, useState } from "react";

import { ArrowUp, Mic, Plus } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/cn";

interface ChatComposerProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  showContextButton?: boolean;
  showMicrophoneButton?: boolean;
}

export function ChatComposer({
  onSend,
  disabled,
  value,
  onChange,
  placeholder,
  showContextButton = true,
  showMicrophoneButton = true,
}: ChatComposerProps) {
  const [uncontrolledValue, setUncontrolledValue] = useState("");
  const isControlled = typeof value === "string" && typeof onChange === "function";
  const message = isControlled ? value : uncontrolledValue;
  const trimmedMessage = useMemo(() => message.trim(), [message]);

  const updateMessage = (next: string) => {
    if (isControlled && onChange) {
      onChange(next);
    } else {
      setUncontrolledValue(next);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmedMessage) return;
    onSend(trimmedMessage);
    updateMessage("");
  };

  const inactiveIcon = trimmedMessage.length === 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full items-center gap-3 rounded-full border border-border/50 bg-background px-4 py-2 text-sm shadow-sm"
    >
      {showContextButton && (
        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground transition hover:text-foreground"
          title="Ajouter un contexte"
        >
          <Plus className="h-4 w-4" />
        </button>
      )}
      <Textarea
        rows={1}
        value={message}
        onChange={(event) => updateMessage(event.target.value)}
        placeholder={placeholder ?? "Demander des modifications ou poser une question..."}
        disabled={disabled}
        className="max-h-28 min-h-0 flex-1 resize-none border-none bg-transparent px-0 py-0 text-sm shadow-none focus-visible:ring-0"
      />
      {showMicrophoneButton && (
        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition hover:text-foreground"
          title="Micro"
        >
          <Mic className="h-4 w-4" />
        </button>
      )}
      <button
        type="submit"
        disabled={disabled || inactiveIcon}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground transition disabled:cursor-not-allowed disabled:opacity-60",
          !inactiveIcon && "bg-primary text-primary-foreground"
        )}
      >
        <ArrowUp className="h-4 w-4" />
      </button>
    </form>
  );
}
