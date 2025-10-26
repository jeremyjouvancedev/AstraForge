import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatComposerProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}

export function ChatComposer({ onSend, disabled, value, onChange, placeholder }: ChatComposerProps) {
  const [uncontrolledValue, setUncontrolledValue] = useState("");
  const isControlled = typeof value === "string" && typeof onChange === "function";
  const message = isControlled ? value : uncontrolledValue;

  const updateMessage = (next: string) => {
    if (isControlled && onChange) {
      onChange(next);
    } else {
      setUncontrolledValue(next);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!message.trim()) return;
    onSend(message);
    updateMessage("");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <Textarea
        rows={4}
        value={message}
        onChange={(event) => updateMessage(event.target.value)}
        placeholder={placeholder ?? "Ask questions, refine the spec, or provide approvals."}
        disabled={disabled}
      />
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={disabled || message.length === 0}>
          Send
        </Button>
      </div>
    </form>
  );
}
