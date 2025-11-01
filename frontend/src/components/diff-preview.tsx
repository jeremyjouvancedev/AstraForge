import { useMemo } from "react";

import { cn } from "@/lib/cn";

interface DiffPreviewProps {
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

export function DiffPreview({ diff, className, maxHeight = 360 }: DiffPreviewProps) {
  const rows = useMemo<DiffRow[]>(() => {
    if (!diff) {
      return [];
    }

    const result: DiffRow[] = [];
    let leftLine = 0;
    let rightLine = 0;
    let removedBuffer: string[] = [];
    let addedBuffer: string[] = [];

    const flushBuffers = () => {
      if (!removedBuffer.length && !addedBuffer.length) {
        return;
      }
      const count = Math.max(removedBuffer.length, addedBuffer.length);
      for (let i = 0; i < count; i += 1) {
        const removal = removedBuffer[i];
        const addition = addedBuffer[i];
        const leftNumber = removal !== undefined ? leftLine : null;
        const rightNumber = addition !== undefined ? rightLine : null;
        if (removal !== undefined) {
          leftLine += 1;
        }
        if (addition !== undefined) {
          rightLine += 1;
        }
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

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border/60 bg-muted/30 text-foreground",
        className
      )}
    >
      {hasContent ? (
        <div className="overflow-auto" style={{ maxHeight }}>
          <div className="grid grid-cols-[60px_minmax(0,1fr)_60px_minmax(0,1fr)] bg-muted/50 text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">
            <div className="col-span-2 border-r border-border/60 px-4 py-2">Original</div>
            <div className="col-span-2 px-4 py-2">Updated</div>
          </div>
          {rows.map((row, index) => {
            if (row.type === "meta") {
              return (
                <div
                  key={`meta-${index}`}
                  className={cn(
                    "col-span-full px-4 py-2 text-xs font-mono",
                    row.variant === "hunk" && "bg-sky-500/10 text-sky-100 font-semibold",
                    row.variant === "file" && "bg-muted/70 text-muted-foreground font-semibold",
                    row.variant === "info" && "bg-muted/40 text-muted-foreground"
                  )}
                >
                  {row.text}
                </div>
              );
            }

            return (
              <div
                key={`content-${index}`}
                className="grid grid-cols-[60px_minmax(0,1fr)_60px_minmax(0,1fr)] border-t border-border/50 font-mono text-xs leading-relaxed"
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
      ) : (
        <div className="px-4 py-6 text-xs text-muted-foreground">
          Diff preview not available yet.
        </div>
      )}
    </div>
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
    "border-r border-border/40 px-2 py-1 text-right text-[0.65rem] font-semibold text-muted-foreground/70",
    variant === "added" && "bg-emerald-500/15 text-emerald-200",
    variant === "removed" && "bg-red-500/15 text-red-200",
    variant === "context" && "bg-muted/30"
  );

  const textClasses = cn(
    "whitespace-pre-wrap break-words px-3 py-1",
    variant === "added" && "bg-emerald-500/10 text-emerald-100",
    variant === "removed" && "bg-red-500/10 text-red-100",
    variant === "context" && "text-foreground/90",
    isRight && "border-l border-border/40"
  );

  return (
    <>
      <div className={numberClasses}>{number != null ? number : ""}</div>
      <div className={textClasses}>{text || "\u00A0"}</div>
    </>
  );
}
