import type { HTMLAttributes } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

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
  user: "border-primary/40 bg-primary/10 text-primary-foreground",
  assistant: "border-secondary/30 bg-background text-foreground",
  system: "border-muted bg-muted text-muted-foreground"
};

const markdownComponents: Components = {
  h1: ({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) => (
    <h1
      {...props}
      className={cn(
        "mt-4 border-b border-border pb-1 text-xl font-semibold text-foreground",
        className
      )}
    />
  ),
  h2: ({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) => (
    <h2
      {...props}
      className={cn(
        "mt-4 border-b border-border/80 pb-1 text-lg font-semibold text-foreground",
        className
      )}
    />
  ),
  h3: ({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) => (
    <h3
      {...props}
      className={cn("mt-3 text-base font-semibold text-foreground", className)}
    />
  ),
  h4: ({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) => (
    <h4
      {...props}
      className={cn("mt-3 text-sm font-semibold text-foreground", className)}
    />
  ),
  p: ({ ...props }) => (
    <p
      {...props}
      className={cn("my-3 leading-relaxed text-muted-foreground", props.className)}
    />
  ),
  strong: ({ ...props }) => (
    <strong {...props} className={cn("font-semibold text-foreground", props.className)} />
  ),
  em: ({ ...props }) => (
    <em {...props} className={cn("text-foreground/80", props.className)} />
  ),
  blockquote: ({ ...props }) => (
    <blockquote
      {...props}
      className={cn(
        "my-4 border-l-4 border-border/70 bg-muted/40 px-4 py-2 text-sm italic text-muted-foreground",
        props.className
      )}
    />
  ),
  ul: ({ ...props }) => (
    <ul
      {...props}
      className={cn("my-3 list-disc space-y-1 pl-5 text-foreground", props.className)}
    />
  ),
  ol: ({ ...props }) => (
    <ol
      {...props}
      className={cn("my-3 list-decimal space-y-1 pl-5 text-foreground", props.className)}
    />
  ),
  li: ({ ...props }) => (
    <li {...props} className={cn("leading-relaxed", props.className)} />
  ),
  code: ({ children, inline, className, ...props }) => {
    if (inline) {
      return (
        <code
          {...props}
          className={cn(
            "inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/70 px-1.5 py-0.5 text-[0.92em] font-mono text-foreground dark:bg-muted/60",
            className
          )}
        >
          <span aria-hidden="true" className="text-muted-foreground/80">
            `
          </span>
          <span>{children}</span>
          <span aria-hidden="true" className="text-muted-foreground/80">
            `
          </span>
        </code>
      );
    }
    return (
      <code {...props} className={cn("font-mono text-xs leading-relaxed", className)}>
        {children}
      </code>
    );
  },
  pre: ({ className, children, ...props }) => (
    <pre
      {...props}
      className={cn(
        "my-3 overflow-auto rounded-xl border border-border bg-[#f6f8fa] px-0 py-0 text-sm text-foreground dark:bg-muted",
        className
      )}
    >
      <code className="block whitespace-pre px-4 py-3 font-mono text-xs leading-relaxed text-foreground">
        {children}
      </code>
    </pre>
  ),
  table: ({ ...props }) => (
    <div className="my-4 overflow-hidden rounded-xl border border-border">
      <table {...props} className="w-full text-left text-sm text-foreground" />
    </div>
  ),
  thead: ({ ...props }) => (
    <thead {...props} className={cn("bg-muted/70 text-foreground", props.className)} />
  ),
  th: ({ ...props }) => (
    <th
      {...props}
      className={cn("border-b border-border px-3 py-2 text-xs font-semibold", props.className)}
    />
  ),
  td: ({ ...props }) => (
    <td
      {...props}
      className={cn("border-b border-border/60 px-3 py-2 text-xs", props.className)}
    />
  ),
  a: ({ ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "text-primary underline underline-offset-2 transition hover:text-primary/80",
        props.className
      )}
    >
      {props.children}
    </a>
  ),
};

export function ChatTimeline({ messages = [] }: ChatTimelineProps) {
  if (messages.length === 0) {
    return <Card className="p-6 text-sm text-muted-foreground">No messages yet.</Card>;
  }

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <div
          key={message.id}
          className={cn(
            "flex w-full",
            message.role === "user" ? "justify-end" : "justify-start"
          )}
        >
          <Card
            className={cn(
              "max-w-[85%] rounded-3xl border px-4 py-3 shadow-sm transition",
              roleStyles[message.role] ?? roleStyles.assistant
            )}
          >
            <CardContent className="space-y-2 p-0">
              <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
                <span className="font-semibold">{message.role}</span>
                <time dateTime={message.created_at}>
                  {Number.isNaN(Date.parse(message.created_at))
                    ? message.created_at
                    : new Date(message.created_at).toLocaleTimeString()}
                </time>
              </div>
              <ReactMarkdown
                className="space-y-3 text-sm leading-relaxed"
                skipHtml
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {message.content}
              </ReactMarkdown>
            </CardContent>
          </Card>
        </div>
      ))}
    </div>
  );
}
