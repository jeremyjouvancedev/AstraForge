import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatComposerProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatComposer({ onSend, disabled }: ChatComposerProps) {
  const [message, setMessage] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!message.trim()) return;
    onSend(message.trim());
    setMessage("");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <Textarea
        rows={4}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="Ask questions, refine the spec, or provide approvals."
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
