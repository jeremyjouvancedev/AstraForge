import { useMemo } from "react";
import { Info } from "lucide-react";

import { cn } from "@/lib/cn";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

export interface DiffPreviewProps {
  diff?: string;
  className?: string;
  maxHeight?: number;
}

type DiffVariant = "added" | "removed" | "context";

type DiffRow =
  | {
      type: "meta";
      text: string;
      variant: "hunk" | "file" | "info";
    }
  | {
      type: "content";
      leftText: string;
      rightText: string;
      leftNumber: number | null;
      rightNumber: number | null;
      leftVariant: DiffVariant;
      rightVariant: DiffVariant;
    };

const HUNK_REGEX = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function DiffPreview({
  diff,
  className,
  maxHeight = 360,
}: DiffPreviewProps) {
  const rows = useMemo<DiffRow[]>(() => {
    if (!diff) return [];

    const result: DiffRow[] = [];
    let leftLine = 0;
    let rightLine = 0;
    let removedBuffer: string[] = [];
    let addedBuffer: string[] = [];

    const flushBuffers = () => {
      if (!removedBuffer.length && !addedBuffer.length) return;

      const count = Math.max(removedBuffer.length, addedBuffer.length);

      for (let i = 0; i < count; i += 1) {
        const removal = removedBuffer[i];
        const addition = addedBuffer[i];
        const leftNumber = removal !== undefined ? leftLine : null;
        const rightNumber = addition !== undefined ? rightLine : null;

        if (removal !== undefined) leftLine += 1;
        if (addition !== undefined) rightLine += 1;

        result.push({
          type: "content",
          leftText: removal ?? "",
          rightText: addition ?? "",
          leftNumber,
          rightNumber,
          leftVariant: removal !== undefined ? "removed" : "context",
          rightVariant: addition !== undefined ? "added" : "context",
        });
      }

      removedBuffer = [];
      addedBuffer = [];
    };

    const pushMeta = (text: string, variant: "hunk" | "file" | "info") => {
      flushBuffers();
      result.push({ type: "meta", text, variant });
    };

    diff.split(/\r?\n/).forEach((rawLine) => {
      if (rawLine.startsWith("diff ") || rawLine.startsWith("index ")) {
        pushMeta(rawLine, "info");
        return;
      }

      if (rawLine.startsWith("--- ") || rawLine.startsWith("+++ ")) {
        pushMeta(rawLine, "file");
        return;
      }

      if (rawLine.startsWith("@@")) {
        const match = HUNK_REGEX.exec(rawLine);
        if (match) {
          leftLine = Number.parseInt(match[1], 10);
          rightLine = Number.parseInt(match[2], 10);
        }
        pushMeta(rawLine, "hunk");
        return;
      }

      if (rawLine.startsWith("-")) {
        if (addedBuffer.length && removedBuffer.length === 0) {
          flushBuffers();
        }
        removedBuffer.push(rawLine.slice(1));
        return;
      }

      if (rawLine.startsWith("+")) {
        addedBuffer.push(rawLine.slice(1));
        return;
      }

      if (rawLine.startsWith("\\ No newline at end of file")) {
        pushMeta(rawLine, "info");
        return;
      }

      const line = rawLine.startsWith(" ") ? rawLine.slice(1) : rawLine;
      flushBuffers();
      result.push({
        type: "content",
        leftText: line,
        rightText: line,
        leftNumber: leftLine,
        rightNumber: rightLine,
        leftVariant: "context",
        rightVariant: "context",
      });
      leftLine += 1;
      rightLine += 1;
    });

    flushBuffers();
    return result;
  }, [diff]);

  const hasContent = rows.some((row) => row.type === "content");

  const stats = useMemo(() => {
    let added = 0;
    let removed = 0;

    rows.forEach((row) => {
      if (row.type !== "content") return;
      if (row.leftVariant === "removed") removed += 1;
      if (row.rightVariant === "added") added += 1;
    });

    return { added, removed };
  }, [rows]);

  return (
    <Card
      className={cn(
        "overflow-hidden border-border/70 bg-background/80 shadow-sm",
        className
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between border-b bg-muted/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-[0.7rem] font-semibold uppercase tracking-wide text-foreground/80">
            Diff preview
          </CardTitle>
          <span className="h-1 w-1 rounded-full bg-muted-foreground/60" />
          <span className="text-[0.7rem] text-foreground/70">
            {hasContent
              ? "Side-by-side comparison"
              : "Waiting for changes to compare"}
          </span>
        </div>

        {hasContent && (
          <div className="flex items-center gap-1">
            <Badge
              variant="outline"
              className="h-5 border-emerald-500/60 bg-emerald-500/10 px-2 text-[0.7rem] font-semibold text-emerald-600 dark:text-emerald-400"
            >
              +{stats.added} added
            </Badge>
            <Badge
              variant="outline"
              className="h-5 border-destructive/70 bg-destructive/10 px-2 text-[0.7rem] font-semibold text-destructive"
            >
              -{stats.removed} removed
            </Badge>
          </div>
        )}
      </CardHeader>

      <CardContent className="p-0">
        {hasContent ? (
          <ScrollArea style={{ maxHeight }}>
            <div
              className="min-w-full text-xs"
              style={{
                fontFamily:
                  "ui-monospace, Menlo, Monaco, 'Cascadia Code', 'Fira Code', monospace",
              }}
            >
              {/* Sticky header */}
              <div className="sticky top-0 z-10 grid grid-cols-[60px_minmax(0,1fr)_60px_minmax(0,1fr)] border-b border-border/70 bg-muted/90 text-[0.7rem] font-semibold uppercase tracking-wide text-foreground/80 backdrop-blur">
                <div className="col-span-2 flex items-center gap-1 border-r border-border/70 px-3 py-2">
                  <span className="inline-block h-2 w-2 rounded-full bg-destructive" />
                  <span>Original</span>
                </div>
                <div className="col-span-2 flex items-center gap-1 px-3 py-2">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                  <span>Updated</span>
                </div>
              </div>

              {/* Rows */}
              {rows.map((row, index) => {
                if (row.type === "meta") {
                  return (
                    <div
                      key={`meta-${index}`}
                      className={cn(
                        "grid grid-cols-[60px_minmax(0,1fr)_60px_minmax(0,1fr)] border-b border-border/40 text-[0.7rem] font-mono",
                        row.variant === "hunk" &&
                          "bg-sky-500/10 text-sky-500 font-semibold",
                        row.variant === "file" &&
                          "bg-muted/80 text-foreground/80 font-semibold",
                        row.variant === "info" &&
                          "bg-background/90 text-foreground/70"
                      )}
                    >
                      <div className="col-span-4 px-3 py-1.5">{row.text}</div>
                    </div>
                  );
                }

                return (
                  <div
                    key={`content-${index}`}
                    className="group grid grid-cols-[60px_minmax(0,1fr)_60px_minmax(0,1fr)] border-b border-border/40 font-mono text-[0.75rem] font-medium leading-relaxed hover:bg-muted/30"
                  >
                    <DiffCell
                      number={row.leftNumber}
                      text={row.leftText}
                      variant={row.leftVariant}
                    />
                    <DiffCell
                      number={row.rightNumber}
                      text={row.rightText}
                      variant={row.rightVariant}
                      isRight
                    />
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        ) : (
          <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
              <Info className="h-4 w-4 text-foreground/70" />
            </div>
            <p className="text-sm font-semibold text-foreground/80">
              Diff preview not available yet
            </p>
            <p className="max-w-sm text-xs text-foreground/70">
              Once you generate or select a change, you&apos;ll see a
              side-by-side comparison of the original and updated content here.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface DiffCellProps {
  number: number | null;
  text: string;
  variant: DiffVariant;
  isRight?: boolean;
}

function DiffCell({ number, text, variant, isRight = false }: DiffCellProps) {
  const numberClasses = cn(
    "flex items-start justify-end border-r border-border/40 px-2 py-1 text-[0.7rem] font-semibold text-foreground/80",
    variant === "added" && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    variant === "removed" &&
      "bg-destructive/10 text-destructive-700 dark:text-destructive-300",
    variant === "context" && "bg-muted/60 text-foreground/70"
  );

  const textClasses = cn(
    "whitespace-pre-wrap break-words px-3 py-1 transition-colors",
    variant === "added" &&
      "border-l-2 border-emerald-500 bg-emerald-500/10 text-emerald-900 dark:text-emerald-100",
    variant === "removed" &&
      "border-l-2 border-destructive bg-destructive/10 text-destructive-900 dark:text-destructive-100",
    variant === "context" && "bg-card text-foreground/90",
    isRight && "border-l border-border/40"
  );

  return (
    <>
      <div className={numberClasses}>{number != null ? number : ""}</div>
      <div className={textClasses}>{text || "\u00A0"}</div>
    </>
  );
}
