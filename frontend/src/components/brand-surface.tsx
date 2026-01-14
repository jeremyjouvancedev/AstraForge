import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const glowTopStyle = {
  background:
    "radial-gradient(circle at 30% 30%, rgba(99,102,241,.35), transparent 55%), radial-gradient(circle at 70% 50%, rgba(168,85,247,.28), transparent 60%), radial-gradient(circle at 50% 80%, rgba(34,211,238,.18), transparent 60%)"
};

const glowBottomStyle = {
  background:
    "radial-gradient(circle at 45% 40%, rgba(99,102,241,.18), transparent 60%), radial-gradient(circle at 60% 60%, rgba(168,85,247,.16), transparent 60%)"
};

type BrandSurfaceProps = {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  glow?: "soft" | "bold";
};

export default function BrandSurface({
  children,
  className,
  contentClassName,
  glow = "soft"
}: BrandSurfaceProps) {
  return (
    <div
      className={cn(
        "relative z-0 min-h-screen overflow-hidden bg-zinc-950 text-zinc-100 antialiased",
        className
      )}
      style={{ colorScheme: "dark" }}
    >
      <div className="pointer-events-none absolute inset-0 -z-20 overflow-hidden">
        <div className="absolute inset-0 home-noise opacity-25" />
        <div className="absolute inset-0 home-grid opacity-20" />
        <div
          className={cn(
            "absolute -top-48 left-1/2 h-[560px] w-[960px] -translate-x-1/2 rounded-full blur-3xl transition-opacity duration-500",
            glow === "bold" ? "opacity-80" : "opacity-60"
          )}
          style={glowTopStyle}
        />
        <div
          className={cn(
            "absolute -bottom-64 left-1/2 h-[620px] w-[1040px] -translate-x-1/2 rounded-full blur-3xl transition-opacity duration-500",
            glow === "bold" ? "opacity-70" : "opacity-50"
          )}
          style={glowBottomStyle}
        />
      </div>

      <div className={cn("relative z-10 h-full w-full", contentClassName)}>{children}</div>
    </div>
  );
}
