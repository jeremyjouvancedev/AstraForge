import { Card, CardContent } from "@/components/ui/card";

interface ChatMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

interface ChatTimelineProps {
  messages?: ChatMessage[];
}

const roleStyles: Record<string, string> = {
  user: "border-primary/20 bg-primary/5",
  assistant: "border-secondary/40 bg-secondary/10",
  system: "border-muted bg-muted"
};

export function ChatTimeline({ messages = [] }: ChatTimelineProps) {
  if (messages.length === 0) {
    return <Card className="p-6 text-sm text-muted-foreground">No messages yet.</Card>;
  }

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <Card key={message.id} className={`border ${roleStyles[message.role] ?? ""}`}>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between text-xs uppercase text-muted-foreground">
              <span>{message.role}</span>
              <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString()}</time>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
